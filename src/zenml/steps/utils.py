#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.

"""
The collection of utility functions/classes are inspired by their original
implementation of the Tensorflow Extended team, which can be found here:

https://github.com/tensorflow/tfx/blob/master/tfx/dsl/component/experimental
/decorators.py

This version is heavily adjusted to work with the Pipeline-Step paradigm which
is proposed by ZenML.
"""

from __future__ import absolute_import, division, print_function

import inspect
import json
import sys
from typing import Any, Callable, Dict, List, Optional

from tfx import types as tfx_types
from tfx.dsl.component.experimental.decorators import _SimpleComponent
from tfx.dsl.components.base.base_executor import BaseExecutor
from tfx.dsl.components.base.executor_spec import ExecutorClassSpec
from tfx.types import component_spec
from tfx.types.channel import Channel
from tfx.utils import json_utils

from zenml.materializers.base_materializer import BaseMaterializer
from zenml.materializers.default_materializer_registry import (
    default_materializer_factory,
)
from zenml.steps.base_step_config import BaseStepConfig
from zenml.steps.step_output import Output

STEP_INNER_FUNC_NAME: str = "process"
SINGLE_RETURN_OUT_NAME: str = "output"


class _PropertyDictWrapper(json_utils.Jsonable):
    """Helper class to wrap inputs/outputs from TFX nodes.
    Currently, this class is read-only (setting properties is not implemented).
    Internal class: no backwards compatibility guarantees.
    Code Credit: https://github.com/tensorflow/tfx/blob
    /51946061ae3be656f1718a3d62cd47228b89b8f4/tfx/types/node_common.py
    """

    def __init__(
        self,
        data: Dict[str, Channel],
        compat_aliases: Optional[Dict[str, str]] = None,
    ):
        """Initializes the wrapper object.

        Args:
            data: The data to be wrapped.
            compat_aliases: Compatability aliases to support deprecated keys.
        """
        self._data = data
        self._compat_aliases = compat_aliases or {}

    def __iter__(self):
        """Returns a generator that yields keys of the wrapped dictionary."""
        yield from self._data

    def __getitem__(self, key):
        """Returns the dictionary value for the specified key."""
        if key in self._compat_aliases:
            key = self._compat_aliases[key]
        return self._data[key]

    def __getattr__(self, key):
        """Returns the dictionary value for the specified key."""
        if key in self._compat_aliases:
            key = self._compat_aliases[key]
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError

    def __repr__(self) -> str:
        """Returns the representation of the wrapped dictionary."""
        return repr(self._data)

    def get_all(self) -> Dict[str, Channel]:
        """Returns the wrapped dictionary."""
        return self._data

    def keys(self):
        """Returns the keys of the wrapped dictionary."""
        return self._data.keys()

    def values(self):
        """Returns the values of the wrapped dictionary."""
        return self._data.values()

    def items(self):
        """Returns the items of the wrapped dictionary."""
        return self._data.items()


class _ZenMLSimpleComponent(_SimpleComponent):
    """Simple ZenML TFX component with outputs overridden."""

    @property
    def outputs(self) -> _PropertyDictWrapper:
        """Returns the wrapped spec outputs."""
        return _PropertyDictWrapper(self.spec.outputs)


class _FunctionExecutor(BaseExecutor):
    """Base TFX Executor class which is compatible with ZenML steps"""

    _FUNCTION = staticmethod(lambda: None)

    def resolve_materializer(
        self, obj_type: Any, artifact: tfx_types.Artifact
    ) -> BaseMaterializer:
        """Resolves the materializer for the given obj_type.

        Args:
            obj_type: Type of object..
            artifact: A TFX artifact type.

        Returns:
            The right materializer based on the defaults or optionally the one
            set by the user.
        """
        materializer_class = (
            default_materializer_factory.get_single_materializer_type(obj_type)
        )
        return materializer_class(artifact)

    def resolve_input_artifact(
        self, obj_type: Any, artifact: tfx_types.Artifact
    ) -> Any:
        """Resolves an input artifact, i.e., reading it from the Artifact Store
        to a pythonic object.

        Args:
            obj_type: Type of object.
            artifact: A TFX artifact type.

        Returns:
            Return the output of `handle_input()` of selected materializer.
        """
        materializer = self.resolve_materializer(obj_type, artifact)
        # The materializer now returns a resolved input
        return materializer.handle_input()

    def resolve_output_artifact(
        self, obj_type: Any, artifact: tfx_types.Artifact, data: Any
    ) -> None:
        """Resolves an output artifact, i.e., writing it to the Artifact Store.
        Calls `handle_return(return_values)` of the selected materializer.

        Args:
            obj_type: Type of object.
            artifact: A TFX artifact type.
            data: The object to be passed to `handle_return()`.
        """
        materializer = self.resolve_materializer(obj_type, artifact)
        materializer.handle_return(data)

    def Do(
        self,
        input_dict: Dict[str, List[tfx_types.Artifact]],
        output_dict: Dict[str, List[tfx_types.Artifact]],
        exec_properties: Dict[str, Any],
    ):
        """Main block for the execution of the step

        Args:
            input_dict: dictionary containing the input artifacts
            output_dict: dictionary containing the output artifacts
            exec_properties: dictionary containing the execution parameters
        """

        # Building the args for the process function
        function_params = {}

        # First, we parse the inputs, i.e., params and input artifacts.
        spec = inspect.getfullargspec(self._FUNCTION)
        args = spec.args
        for arg in args:
            arg_type = spec.annotations.get(arg, None)
            if issubclass(arg_type, BaseStepConfig):
                # Resolving the execution parameters
                new_exec = {
                    k: json.loads(v) for k, v in exec_properties.items()
                }
                config_object = arg_type.parse_obj(new_exec)
                function_params[arg] = config_object
            else:
                # At this point, it has to be an artifact, so we resolve
                function_params[arg] = self.resolve_input_artifact(
                    arg_type, input_dict[arg][0]
                )

        return_values = self._FUNCTION(**function_params)
        spec = inspect.getfullargspec(self._FUNCTION)
        return_type = spec.annotations.get("return", None)
        if return_type is not None:
            if isinstance(return_type, Output):
                # Resolve named (and multi-) outputs.
                for i, output_tuple in enumerate(return_type.items()):
                    self.resolve_output_artifact(
                        output_tuple[1],
                        output_dict[output_tuple[0]][0],
                        return_values[i],  # order preserved.
                    )
            else:
                # Resolve single output
                self.resolve_output_artifact(
                    return_type,
                    output_dict[SINGLE_RETURN_OUT_NAME][0],
                    return_values,
                )


def generate_component(step) -> Callable[..., Any]:
    """Utility function which converts a ZenML step into a TFX Component

    Args:
        step: a ZenML step instance

    Returns:
        component: the class of the corresponding TFX component
    """

    # Managing the parameters for component spec creation
    spec_inputs, spec_outputs, spec_params = {}, {}, {}
    for key, artifact_type in step.INPUT_SPEC.items():
        spec_inputs[key] = component_spec.ChannelParameter(type=artifact_type)
    for key, artifact_type in step.OUTPUT_SPEC.items():
        spec_outputs[key] = component_spec.ChannelParameter(type=artifact_type)
    for key, prim_type in step.PARAM_SPEC.items():
        spec_params[key] = component_spec.ExecutionParameter(type=str)

    component_spec_class = type(
        "%s_Spec" % step.__class__.__name__,
        (tfx_types.ComponentSpec,),
        {
            "INPUTS": spec_inputs,
            "OUTPUTS": spec_outputs,
            "PARAMETERS": spec_params,
        },
    )

    # Defining a executor class bu utilizing the process function
    executor_class = type(
        "%s_Executor" % step.__class__.__name__,
        (_FunctionExecutor,),
        {
            "_FUNCTION": staticmethod(getattr(step, STEP_INNER_FUNC_NAME)),
            "__module__": step.__module__,
        },
    )

    module = sys.modules[step.__module__]
    setattr(module, "%s_Executor" % step.__class__.__name__, executor_class)
    executor_spec_instance = ExecutorClassSpec(executor_class=executor_class)

    # Defining the component with the corresponding executor and spec
    return type(
        step.__class__.__name__,
        (_ZenMLSimpleComponent,),
        {
            "SPEC_CLASS": component_spec_class,
            "EXECUTOR_SPEC": executor_spec_instance,
            "__module__": step.__module__,
        },
    )
