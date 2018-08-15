# Copyright 2018 Xanadu Quantum Technologies Inc.
r"""
ProjectQ plugin
========================

**Module name:** :mod:`openqml.plugins.projectq`

.. currentmodule:: openqml.plugins.projectq

This plugin provides the interface between OpenQML and ProjecQ.
It enables OpenQML to optimize quantum circuits simulable with ProjectQ.

ProjecQ supports several different backends. Of those, the following are useful in the current context:

- projectq.backends.Simulator([gate_fusion, ...])	Simulator is a compiler engine which simulates a quantum computer using C++-based kernels.
- projectq.backends.ClassicalSimulator()	        A simple introspective simulator that only permits classical operations.
- projectq.backends.IBMBackend([use_hardware, ...])	The IBM Backend class, which stores the circuit, transforms it to JSON QASM, and sends the circuit through the IBM API.

See PluginAPI._capabilities['backend'] for a list of backend options.

Functions
---------

.. autosummary::
   init_plugin

Classes
-------

.. autosummary::
   Gate
   Observable
   PluginAPI

----
"""

import logging as log

import numpy as np
from numpy.random import (randn,)

import openqml.plugin
from openqml.circuit import (GateSpec, Command, ParRef, Circuit)

import projectq as pq


class Gate(GateSpec): # pylint: disable=too-few-public-methods
    """Implements the quantum gates and observables.
    """
    def __init__(self, name, n_sys, n_par, cls=None, par_domain='R'): # pylint: disable=too-many-arguments
        super().__init__(name, n_sys, n_par, grad_method='F', par_domain=par_domain)
        self.cls = cls  #: class: pq subclass corresponding to the gate

    def execute(self, par, reg, sim):
        """Applies a single gate or measurement on the current system state.

        Args:
          par (Sequence[float]): gate parameters
          reg   (Sequence[int]): subsystems to which the gate is applied
          sim (~openqml.plugin.PluginAPI): simulator instance keeping track of the system state and measurement results
        """
        G = self.cls(*par)
        reg = tuple(reg)
        G | reg


class Observable(Gate): # pylint: disable=too-few-public-methods
    """Implements hermitian observables.

    We assume that all the observables in the circuit are consequtive, and commute.
    Since we are only interested in the expectation values, there is no need to project the state after the measurement.
    See :ref:`measurements`.
    """
    def execute(self, par, reg, sim):
        """Estimates the expectation value of the observable in the current system state.

        Args:
          par (Sequence[float]): gate parameters
          reg   (Sequence[int]): subsystems to which the gate is applied
          sim (~openqml.plugin.PluginAPI): simulator instance keeping track of the system state and measurement results
        """
        backend = type(sim.eng.backend).__name__

        if backend == 'IBMBackend' and hasattr(sim.eng, 'already_a_measurement_performed') and sim.eng.already_a_measurement_performed ==True :
            raise NotImplementedError("Only a single measurement is possible on the IBMBackend.")
        else:
            sim.eng.already_a_measurement_performed = True

        if self.n_sys != 1 and backend != 'IBMBackend':
            raise ValueError('This plugin with the %s backend supports only single qubit observables.', backend)

        if backend == 'Simulator':
            sim.eng.flush(deallocate_qubits=False)
            if self.cls == pq.ops.X or self.cls == pq.ops.Y or self.cls == pq.ops.Z:
                expectation_value = sim.eng.backend.get_expectation_value(pq.ops.QubitOperator(str(self.cls)+'0'), reg)
                variance = 1 - expectation_value**2
            elif self.cls == AllZClass:
                expectation_value = [ sim.eng.backend.get_expectation_value(pq.ops.QubitOperator(str(pq.ops.Z)+'0'), [qubit]) for qubit in sim.reg]
                variance = [1 - e**2 for e in expectation_value]
            else:
                raise NotImplementedError("Estimation of expectation values not yet implemented for the observable {} in backend {}.".format(self.cls, backend))
        elif backend == 'ClassicalSimulator':
            sim.eng.flush(deallocate_qubits=False)
            if self.cls == pq.ops.Z:
                expectation_value = sim.eng.backend.read_bit(reg[0])
                variance = 0
            else:
                raise NotImplementedError("Estimation of expectation values not yet implemented for the observable {} in backend {}.".format(self.cls), backend)
        elif backend == 'IBMBackend':
            #The IBMBackend does not allow multiple measurements, we thus reset it and perform the measurement on the result of a fake circuit
            sim.reset()
            sim.execute_circuit(Circuit([Command(Rx, [0], [i]) for i in range(len(reg))], 'fake identity'))
            sim.eng.flush()
            if self.cls == pq.ops.Z:
                # sim.eng.backend.main_engine.mapper = pq.cengines.LinearMapper(len(reg)) # todo: Find out why ProjectQ does not set a mapper internally. This results in an exception here.
                # probabilities = sim.eng.backend.get_probabilities(reg)
                # print('IBMBackend probabilities'+str(probabilities))
                expectation_value = 0
                variance = 0
            # elif self.cls == AllZClass:
            #     probabilities = sim.eng.backend.get_probabilities(reg)
            #     print('IBMBackend probabilities'+str(probabilities))
            #     expectation_value = 0
            #     variance = 0
            else:
                raise NotImplementedError("Estimation of expectation values not yet implemented for the observable {} in backend {}.".format(self.cls), backend)
        else:
            raise NotImplementedError("Estimation of expectation values not yet implemented for the {} backend.".format(backend))

        log.info('observable: ev: %s, var: %s', expectation_value, variance)
        return expectation_value, variance


class CNOTClass(pq.ops.BasicGate): # pylint: disable=too-few-public-methods
    """Class for the CNOT gate.

    Contrary to other gates, ProjectQ does not have a class for the CNOT gate,
    as it is implemented as a meta-gate.
    For consistency we define this class, whose constructor is made to retun
    a gate with the correct properties by overwriting __new__().
    """
    def __new__(*par): # pylint: disable=no-method-argument
        #return pq.ops.C(pq.ops.XGate())
        return pq.ops.C(pq.ops.NOT)


class CZClass(pq.ops.BasicGate): # pylint: disable=too-few-public-methods
    """Class for the CNOT gate.

    Contrary to other gates, ProjectQ does not have a class for the CZ gate,
    as it is implemented as a meta-gate.
    For consistency we define this class, whose constructor is made to retun
    a gate with the correct properties by overwriting __new__().
    """
    def __new__(*par): # pylint: disable=no-method-argument
        return pq.ops.C(pq.ops.ZGate())

class ToffoliClass(pq.ops.BasicGate): # pylint: disable=too-few-public-methods
    """Class for the Toffoli gate.

    Contrary to other gates, ProjectQ does not have a class for the Toffoli gate,
    as it is implemented as a meta-gate.
    For consistency we define this class, whose constructor is made to retun
    a gate with the correct properties by overwriting __new__().
    """
    def __new__(*par): # pylint: disable=no-method-argument
        return pq.ops.C(pq.ops.ZGate(), 2)

class AllZClass(pq.ops.BasicGate): # pylint: disable=too-few-public-methods
    """Class for the AllZ gate.

    Contrary to other gates, ProjectQ does not have a class for the AllZ gate,
    as it is implemented as a meta-gate.
    For consistency we define this class, whose constructor is made to retun
    a gate with the correct properties by overwriting __new__().
    """
    def __new__(*par): # pylint: disable=no-method-argument
        return pq.ops.Tensor(pq.ops.ZGate())


#gates
H = Gate('H', 1, 0, pq.ops.HGate)
X = Gate('X', 1, 0, pq.ops.XGate)
Y = Gate('Y', 1, 0, pq.ops.YGate)
Z = Gate('Z', 1, 0, pq.ops.ZGate)
S = Gate('S', 1, 0, pq.ops.SGate)
T = Gate('T', 1, 0, pq.ops.TGate)
SqrtX = Gate('SqrtX', 1, 0, pq.ops.SqrtXGate)
Swap = Gate('Swap', 2, 0, pq.ops.SwapGate)
SqrtSwap = Gate('SqrtSwap', 2, 0, pq.ops.SqrtSwapGate)
#Entangle = Gate('Entangle', n, 0, pq.ops.EntangleGate) #This gate acts on all qubits
#Ph = Gate('Ph', 0, 1, pq.ops.Ph) #This gate acts on all qubits or non, depending on how one looks at it...
Rx = Gate('Rx', 1, 1, pq.ops.Rx) #(angle) RotationX gate class
Ry = Gate('Ry', 1, 1, pq.ops.Ry) #(angle) RotationY gate class
Rz = Gate('Rz', 1, 1, pq.ops.Rz) #(angle) RotationZ gate class
R = Gate('R', 1, 1, pq.ops.R) #(angle) Phase-shift gate (equivalent to Rz up to a global phase)
#pq.ops.AllGate , which is the same as pq.ops.Tensor, is a meta gate that acts on all qubits
#pq.ops.QFTGate #This gate acts on all qubits
#pq.ops.QubitOperator #A sum of terms acting on qubits, e.g., 0.5 * ‘X0 X5’ + 0.3 * ‘Z1 Z2’
CRz = Gate('CRz', 2, 1, pq.ops.CRz) #(angle) Shortcut for C(Rz(angle), n=1).
CNOT = Gate('CNOT', 2, 0, CNOTClass)
CZ = Gate('CZ', 2, 0, CZClass)
#Toffoli = Gate('Toffoli', 3, 0, ToffoliClass)
#pq.ops.TimeEvolution #Gate for time evolution under a Hamiltonian (QubitOperator object).
AllZ = Gate('AllZ', 1, 0, AllZClass)

# measurements
MeasureX = Observable('X', 1, 0, pq.ops.X)
MeasureY = Observable('Y', 1, 0, pq.ops.Y)
MeasureZ = Observable('Z', 1, 0, pq.ops.Z)
MeasureAllZ = Observable('AllZ', 1, 0, AllZClass) #todo: 1 should be replaced by a way to specify "all"

demo = [
    Command(Rx,  [0], [ParRef(0)]),
    Command(Rx,  [1], [ParRef(1)]),
    Command(CNOT, [0, 1], []),
]

# circuit templates
_circuit_list = [
    Circuit(demo, 'demo'),
    Circuit(demo +[Command(MeasureZ, [0])], 'demo_ev', out=[0]),
    Circuit(demo +[Command(MeasureZ, [1])], 'demo_ev', out=[1]),
]



class PluginAPI(openqml.plugin.PluginAPI):
    """ProjectQ OpenQML plugin API class.

    Keyword Args:
      backend (str): backend name

    Keyword Args for Simulator backend:
      gate_fusion (bool): If True, gates are cached and only executed once a certain gate-size has been reached (only has an effect for the c++ simulator).
      rnd_seed (int): Random seed (uses random.randint(0, 4294967295) by default).

    Keyword Args for IBMBackend backend:
      use_hardware (bool): If True, the code is run on the IBM quantum chip (instead of using the IBM simulator)
      num_runs (int): Number of runs to collect statistics. (default is 1024)
      verbose (bool): If True, statistics are printed, in addition to the measurement result being registered (at the end of the circuit).
      user (string): IBM Quantum Experience user name
      password (string): IBM Quantum Experience password
      device (string): Device to use (‘ibmqx4’, or ‘ibmqx5’) if use_hardware is set to True. Default is ibmqx4.
      retrieve_execution (int): Job ID to retrieve instead of re-running the circuit (e.g., if previous run timed out).
    """
    plugin_name = 'ProjectQ OpenQML plugin'
    plugin_api_version = '0.1.0'
    plugin_version = '0.1.0'
    author = 'Xanadu Inc.'
    _circuits = {c.name: c for c in _circuit_list}
    #_capabilities = {'backend': list(["Simulator", "ClassicalSimulator", "IBMBackend"])}
    _capabilities = {'backend': list(["Simulator", "IBMBackend"])}

    def __init__(self, name='default', **kwargs):
        super().__init__(name, **kwargs)

        # sensible defaults
        kwargs.setdefault('backend', 'Simulator')


#        kwargs.setdefault('num_runs', 2)
        kwargs.setdefault('verbose', 'True')
#        kwargs.setdefault('device', 'ibmqx4')

        # backend-specific capabilities
        self.backend = kwargs['backend']
        # gate and observable sets depend on the backend, so they have to be instance properties
        gates = [H, X, Y, Z, S, T, SqrtX, Swap, SqrtSwap, Rx, Ry, Rz, R, CRz, CNOT, CZ]
        observables = [MeasureX, MeasureY, MeasureZ, MeasureAllZ]
        if self.backend == 'Simulator':
            pass
        elif self.backend == 'ClassicalSimulator':
            classical_backend = pq.backends.ClassicalSimulator()
            eng = pq.MainEngine(classical_backend)
            with pq.meta.Compute(eng):
                reg = eng.allocate_qureg(max([gate.n_sys for gate in gates]))
                gates = [gate for gate in gates if classical_backend.is_available(pq.ops.Command(eng, gate.cls(*randn(gate.n_par)), [[reg[i]] for i in range(0,gate.n_sys)]))]
            observables = [MeasureZ]
        elif self.backend == 'IBMBackend':
            import inspect
            self.ibm_backend_kwargs = {param:kwargs[param] for param in inspect.signature(pq.backends.IBMBackend).parameters if param in kwargs}
            ibm_backend = pq.backends.IBMBackend(**self.ibm_backend_kwargs)
            eng = pq.MainEngine(ibm_backend)
            with pq.meta.Compute(eng):
                reg = eng.allocate_qureg(max([gate.n_sys for gate in gates]))
                gates = [gate for gate in gates if ((gate.n_par > 0 and ibm_backend.is_available(pq.ops.Command(eng, gate.cls(*randn(gate.n_par)), [[reg[i]] for i in range(0,gate.n_sys)]))) or (gate.n_par==0 and ibm_backend.is_available(pq.ops.Command(eng, gate.cls(), [[reg[i]] for i in range(0,gate.n_sys)]))))]
                gates+=[CNOT]
                # todo: find out why ibm_backend.is_available() returns false for CNOT, see also here: https://github.com/ProjectQ-Framework/ProjectQ/issues/257
                # print('IBM supports the following gates: '+str([gate.name for gate in gates]))
                # print('ibm_backend.is_available(CNOTClass)='+str(ibm_backend.is_available(pq.ops.Command(eng, CNOTClass(), [[reg[0]], [reg[1]]]))) )
                # print('ibm_backend.is_available(CNOT)='+str(ibm_backend.is_available(pq.ops.Command(eng, pq.ops.CNOT, [[reg[0]], [reg[1]]]))) )
                # print('CNOTClass()==NOT: '+str(CNOTClass()==pq.ops.NOT))
                # print('C(NOT)==NOT: '+str(pq.ops.C(pq.ops.NOT)==pq.ops.NOT))
                # print('CNOT==NOT: '+str(pq.ops.CNOT==pq.ops.NOT))
            observables = [MeasureZ]
        else:
            raise ValueError("Unknown backend '{}'.".format(self.backend))

        self._gates = {g.name: g for g in gates}
        self._observables = {g.name: g for g in observables}

        self.init_kwargs = kwargs  #: dict: initialization arguments
        self.eng = None
        self.reg = None

    def __str__(self):
        return super().__str__() +'ProjecQ with Backend: ' +self.backend +'\n'

    def __del__(self):
        self.reset()

    def reset(self):
        """Resets the engine and backend"""
        if self.eng is not None:
            if self.backend == 'Simulator':
                self._deallocate()
            self.eng = None

    def measure(self, observable, reg, par=[], n_eval=0):
        """ """
        return self.expection_value(observable, reg, par, n_eval)

    def expection_value(self, observable, reg, par=[], n_eval=0):
        """Compute the expection value.

        Returns the expectation value of the given observable in the given qubits.

        Args:
          observable (Observable): observable to compute the expectatoin value for
          reg (Sequence[int]): subsystems for which to do the computation
          par (Sequence[float]): parameters of the observable
          n_eval (int): number of samples from which to compute the expectation value
        """
        if isinstance(reg, int):
            reg = [reg]

        temp = self.n_eval  # store the original
        self.n_eval = n_eval

        ev = observable.execute(par, [self.reg[i] for i in reg], self)
        self.n_eval = temp  # restore it
        return ev

    def execute_circuit(self, circuit, params=[], *, reset=True, **kwargs):
        super().execute_circuit(circuit, params, reset=reset, **kwargs)
        circuit = self.circuit

        def parmap(p):
            "Mapping function for gate parameters. Replaces ParRefs with the corresponding parameter values."
            if isinstance(p, ParRef):
                return params[p.idx]
            return p

        # set the required number of subsystems
        if self.eng is None or self.reg is None or self.circuit.n_sys != len(self.reg):
            self.reset()
            if self.backend == 'Simulator':
                backend = pq.backends.Simulator(**kwargs)
            elif self.backend == 'ClassicalSimulator':
                backend = pq.backends.ClassicalSimulator()
            elif self.backend == 'IBMBackend':
                backend = pq.backends.IBMBackend(**self.ibm_backend_kwargs)
            self.eng = pq.MainEngine(backend)
            self.reg = None

        # input the program
        with pq.meta.Compute(self.eng):
            if self.reg is None:
                self.reg = self.eng.allocate_qureg(circuit.n_sys)
            expectation_values = {}
            for cmd in circuit.seq:
                # prepare the parameters
                par = map(parmap, cmd.par)
                if cmd.gate.name not in self._gates and cmd.gate.name not in self._observables:
                    raise ValueError("The cirquit contains the gate {}, which is not supported by the {} backend.".format(cmd.gate.name, self.backend))
                # execute the gate
                expectation_values[tuple(cmd.reg)] = cmd.gate.execute(par, [self.reg[i] for i in cmd.reg], self)

        print('expectation_values='+str(expectation_values))

        if circuit.out is not None:
            # return the estimated expectation values for the requested modes
            return np.array([expectation_values[tuple([idx])] for idx in circuit.out])

    def shutdown(self):
        """Shutdown.

        """
        pass

    def _deallocate(self):
        """Deallocate all qubits to make ProjectQ happy

        See also: https://github.com/ProjectQ-Framework/ProjectQ/issues/2

        Drawback: This is probably rather resource intensive.
        """
        if self.eng is not None and self.backend == 'Simulator':
            pq.ops.All(pq.ops.Measure) | self.reg #avoid an unfriendly error message: https://github.com/ProjectQ-Framework/ProjectQ/issues/2

    def _deallocate2(self):
        """Another proposal for how to deallocate all qubits to make ProjectQ happy

        Unsuitable because: Produces a segmentation fault.
        """
        if self.eng is not None and self.backend == 'Simulator':
             for qubit in self.reg:
                 self.eng.deallocate_qubit(qubit)

    def _deallocate3(self):
        """Another proposal for how to deallocate all qubits to make ProjectQ happy

        Unsuitable because: Throws an error if the probability for the given collapse is 0.
        """
        if self.eng is not None and self.backend == 'Simulator':
            self.eng.flush()
            self.eng.backend.collapse_wavefunction(self.reg, [0 for i in range(len(self.reg))])


def init_plugin():
    """Initialize the plugin.

    Every plugin must define this function.
    It should perform whatever initializations are necessary, and then return an API class.

    Returns:
      class: plugin API class
    """

    return PluginAPI
