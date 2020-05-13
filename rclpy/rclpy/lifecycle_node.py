import rclpy
from rclpy.node import Node

from lifecycle_msgs.msg._state import State
from lifecycle_msgs.msg._transition import Transition
from lifecycle_msgs.msg._transition_description import TransitionDescription

from lifecycle_msgs.srv._get_state import GetState
from lifecycle_msgs.srv._change_state import ChangeState
from lifecycle_msgs.srv._get_available_transitions import GetAvailableTransitions
from lifecycle_msgs.srv._get_available_states import GetAvailableStates
from rclpy.qos import QoSDurabilityPolicy, QoSProfile
import time

from abc import ABC, abstractmethod


class LifecycleNode(Node, ABC):
    """LifecycleNode
    class to inherit Lifecycle-statemachine and services
    :param name: Name hat is passed to Node.__init__
    :type name: String

    """

    def __init__(self, name):
        """__init__ Constructor for LifecycleNodes

        """
        super().__init__(name)
        self._states = {
            "unconfigured" : State(id=State.PRIMARY_STATE_UNCONFIGURED, label="unconfigured"),
            "inactive" : State(id=State.PRIMARY_STATE_INACTIVE, label="inactive"),
            "unknown" : State(id=State.PRIMARY_STATE_UNKNOWN, label="unknown"),
            "active" : State(id=State.PRIMARY_STATE_ACTIVE, label="active"),
            "finalized" : State(id=State.PRIMARY_STATE_FINALIZED, label="finalized"),
            "cleaningup" : State(id=State.TRANSITION_STATE_CLEANINGUP, label="cleaningup"),
            "activating" : State(id=State.TRANSITION_STATE_ACTIVATING, label="activating"),
            "deactivating" : State(id=State.TRANSITION_STATE_DEACTIVATING, label="deactivating"),
            "configuring" : State(id=State.TRANSITION_STATE_CONFIGURING, label="configuring"),
            "errorprocessing" : State(id=State.TRANSITION_STATE_ERRORPROCESSING, label="errorprocessing"),
            "shuttingdown" : State(id=State.TRANSITION_STATE_SHUTTINGDOWN, label="shuttingdown"),
        }
        self._success_state = {
            State.PRIMARY_STATE_UNCONFIGURED: "unconfigured",
            State.TRANSITION_STATE_CLEANINGUP: "unconfigured",
            State.TRANSITION_STATE_ACTIVATING: "active",
            State.TRANSITION_STATE_DEACTIVATING: "inactive",
            State.TRANSITION_STATE_CONFIGURING: "inactive",
            State.TRANSITION_STATE_ERRORPROCESSING: "unconfigured",
            State.TRANSITION_STATE_SHUTTINGDOWN: "finalized",
        }

        self._fail_state = {
            State.TRANSITION_STATE_ERRORPROCESSING: "finalized",
            State.TRANSITION_STATE_ACTIVATING: "inactive",
            State.TRANSITION_STATE_CONFIGURING: "unconfigured",
        }

        latching = QoSProfile(depth=1,
            durability=QoSDurabilityPolicy.RMW_QOS_POLICY_DURABILITY_TRANSIENT_LOCAL)
        self._get_state = self.create_service(GetState, "~/get_state", self._get_state_cb)
        self._change_state = self.create_service(ChangeState, "~/change_state", self._change_state_cb)
        self._get_transitions = self.create_service(GetAvailableTransitions, "~/get_available_transitions", self._available_transitions_cb)
        self._get_states = self.create_service(GetAvailableStates, "~/get_available_states", self._available_states_cb)
        self.lifecycle_publisher = self.create_publisher(State, "~/lifecycle_state", qos_profile=latching)
        print(self._states)
        self._state = self._states['unknown']
        self._transition_callbacks = {
            Transition.TRANSITION_CONFIGURE: self.success,
            Transition.TRANSITION_ACTIVATE: self.success,
        }
        #self._transition(Transition.TRANSITION_CREATE)

    def success(self):
        """success default callback

        :return: just True
        :rtype: bool
        """
        return True
    
    @property
    def _transition_descriptions(self):
        """_transition_descriptions give a list of available transitions
        this is a representation of the state machine transitions!

        :return: List of Transition Descriptions
        :rtype: list(TransitionDescription)
        """
        return [ 
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_CREATE, label="create"),
                start_state=self._states["unknown"],
                goal_state=self._states["unconfigured"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_CONFIGURE, label="configure"),
                start_state=self._states["unconfigured"],
                goal_state=self._states["configuring"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_CREATE, label="create"),
                start_state=self._states["unknown"],
                goal_state=self._states["unconfigured"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_ACTIVATE, label="activate"),
                start_state=self._states["inactive"],
                goal_state=self._states["activating"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_DEACTIVATE, label="deactivate"),
                start_state=self._states["active"],
                goal_state=self._states["deactivating"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_CREATE, label="create"),
                start_state=self._states["unknown"],
                goal_state=self._states["unconfigured"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_ACTIVE_SHUTDOWN, label="shutdown"),
                start_state=self._states["active"],
                goal_state=self._states["shuttingdown"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_INACTIVE_SHUTDOWN, label="shutdown"),
                start_state=self._states["inactive"],
                goal_state=self._states["shuttingdown"]
            ),
            TransitionDescription(
                transition=Transition(id=Transition.TRANSITION_UNCONFIGURED_SHUTDOWN, label="shutdown"),
                start_state=self._states["unconfigured"],
                goal_state=self._states["shuttingdown"]
            ),

            
        ]

    @property
    def _available_transitions(self):
        """_available_transitions Transitions from the current state

        :return: Lift of all transitions out of the current state (that are triggered by the supervisor)
        :rtype: [TransitionDescription]
        """
        return [t for t in self._transition_descriptions if t.start_state == self._state]

    def _transition_done_callback(self, future):
        """_transition_done_callback called after a transition callback is finished

        :param future: future for the result of the callback function
        :type future: Future
        """
        next = None
        try:
            if future.result():
                next = self._success_state[self._state.id]
            else:
                next = self._fail_state[self._state.id]
        except:
            next = "errorprocessing"
        self.change_state(self._states[next])

    def _transition(self, transition):
        """_transition function that executes a given transition

        :param transition: transition id of the required transition
        :type transition: int
        :return: True if the transition exists and is executed
        :rtype: bool
        """
        description = [t for t in self._available_transitions if t.transition.id == transition]
        if len(description) < 1:
            return False
        goal = description[0].goal_state
        self.change_state(goal)
        future = None
        if transition in self._transition_callbacks:
            future = self.executor.create_task(self._transition_callbacks[transition])
        else:
            future = self.executor.create_task(self.success)
        future.add_done_callback(self._transition_done_callback)

        return True

    def change_state(self, new_state):
        """change_state change the internal state to a new value and publish the new state

        :param new_state: State that is assumed
        :type new_state: State
        """
        self.get_logger().info(f"Changing state from {self._state.label} to {new_state.label}")
        self._state = new_state
        self.lifecycle_publisher.publish(self._state)

    def _change_state_cb(self, request, response):
        """_change_state_cb callback for the change_state service

        :param request: service request
        :param response: service repsonse
        :return: True if the transition exists
        """
        #todo: checktransition callback, execute callback if available
        if request.transition.id in [t.transition.id for t in self.current_transitions()]:
            response.success = True
            self._transition(request.transition.id)
        return response

    def _get_state_cb(self, request, response):
        """_get_state_cb callback for the get_state service

        """
        response.current_state = self._state
        return response


    def current_transitions(self):
        """current_transitions transitions from the current state

        :return: the transitions leading out of the current state
        :rtype: [TransitionDescription]
        """
        states = [t for t in self._transition_descriptions if t.start_state == self._state]
        return states 

    def _available_transitions_cb(self, request, response):
        """_available_transitions_cb callback for the available transitions service

        """
        response._available_transitions = self.current_transitions()
        return response

    def _available_states_cb(self, request, repsonse):
        """_available_states_cb callback for the available states service
        """
        repsonse.available_states = list(self._states.values())
        return repsonse
            

class LifecylceSleep(LifecycleNode):
    """LifecylceSleep Test Node for the LifecycleNode
    """
    def __init__(self):
        super().__init__("lc_node")
        self._transition_callbacks[Transition.TRANSITION_ACTIVATE] = self.sleep
        self._transition_callbacks[Transition.TRANSITION_CONFIGURE] = self.sleep

        
    def sleep(self):
        time.sleep(10)
        return True

def main():
    rclpy.init()
    n = LifecylceSleep()
    rclpy.spin(n)

if __name__ == "__main__":
    main()
