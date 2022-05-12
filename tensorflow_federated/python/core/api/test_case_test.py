# Copyright 2018, The TensorFlow Federated Authors.
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

from tensorflow_federated.python.core.api import test_case
from tensorflow_federated.python.core.impl.types import computation_types


empty_struct = computation_types.StructType([])
container_mismatch = (empty_struct,
                      computation_types.StructWithPythonType([], tuple))
named_field = computation_types.StructType([('a', empty_struct)])
unnamed_field = computation_types.StructType([(None, empty_struct)])
naming_mismatch = (named_field, unnamed_field)


class TestUtilsTest(test_case.TestCase):

  def test_types_equivalent_passes_container(self):
    self.assert_types_equivalent(*container_mismatch)

  def test_types_equivalent_fails_naming(self):
    with self.assertRaises(self.failureException):  # pylint: disable=g-error-prone-assert-raises
      self.assert_types_equivalent(*naming_mismatch)

  def test_types_identical_passes_exact(self):
    self.assert_types_identical(empty_struct, empty_struct)

  def test_types_identical_fails_container(self):
    with self.assertRaises(self.failureException):  # pylint: disable=g-error-prone-assert-raises
      self.assert_types_identical(*container_mismatch)

if __name__ == '__main__':
  test_case.main()
