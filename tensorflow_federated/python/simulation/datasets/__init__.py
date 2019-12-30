# Lint as: python3
# Copyright 2019, The TensorFlow Federated Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Datasets for running Federated Learning experiments in simulation."""

from tensorflow_federated.python.simulation.datasets import emnist
from tensorflow_federated.python.simulation.datasets import shakespeare
from tensorflow_federated.python.simulation.datasets import stackoverflow
from tensorflow_federated.python.simulation.datasets.dataset_utils import build_dataset_mixture
from tensorflow_federated.python.simulation.datasets.dataset_utils import build_single_label_dataset
from tensorflow_federated.python.simulation.datasets.dataset_utils import build_synthethic_iid_datasets

# Used by doc generation script.
_allowed_symbols = [
    "build_dataset_mixture",
    "build_single_label_dataset",
    "build_synthethic_iid_datasets",
    "emnist",
    "shakespeare",
    "stackoverflow",
]
