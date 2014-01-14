# -*- coding: utf-8 -*-

# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright (C) 2013 Yahoo! Inc. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from taskflow import exceptions as exc
from taskflow import states
from taskflow import test


class CheckFlowTransitionTest(test.TestCase):

    def test_same_state(self):
        self.assertFalse(
            states.check_flow_transition(states.SUCCESS, states.SUCCESS))

    def test_rerunning_allowed(self):
        self.assertTrue(
            states.check_flow_transition(states.SUCCESS, states.RUNNING))

    def test_no_resuming_from_pending(self):
        self.assertFalse(
            states.check_flow_transition(states.PENDING, states.RESUMING))

    def test_resuming_from_running(self):
        self.assertTrue(
            states.check_flow_transition(states.RUNNING, states.RESUMING))

    def test_bad_transition_raises(self):
        self.assertRaisesRegexp(exc.InvalidState,
                                '^Flow transition.*not allowed',
                                states.check_flow_transition,
                                states.FAILURE, states.SUCCESS)
