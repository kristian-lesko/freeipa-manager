#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: BSD-3-Clause
# Copyright © 2017-2019, GoodData Corporation. All rights reserved.

import logging
import mock
import os
import pytest
import re
from testfixtures import log_capture

import ipamanager.tools.query_tool as tool
import ipamanager.entities as entities
testdir = os.path.dirname(__file__)

modulename = 'ipamanager.tools.query_tool'
CONFIG_CORRECT = os.path.join(testdir, '../freeipa-manager-config/correct')
SETTINGS = os.path.join(testdir, '../freeipa-manager-config/settings.yaml')


class TestQueryTool(object):
    def setup_method(self, method):
        args = ['query', 'member', CONFIG_CORRECT, '-s', SETTINGS,
                '-m', 'user:user1', '-t', 'group:group2']
        with mock.patch('sys.argv', args):
            self.querytool = tool.QueryTool()
        if re.match(r'test_(resolve|build|query|construct)', method.func_name):
            self.querytool._load_config()

    def test_init(self):
        assert self.querytool.args.members == [('user', 'user1')]
        assert self.querytool.args.targets == [('group', 'group2')]

    def test_entity_type(self):
        assert self.querytool._entity_type(
            'sometype:somename') == ('sometype', 'somename')

    def test_entity_type_error_too_few_values(self):
        with pytest.raises(ValueError) as exc:
            self.querytool._entity_type('sometype,somename')
        assert exc.value[0] == 'need more than 1 value to unpack'

    def test_entity_type_error_too_many_values(self):
        with pytest.raises(ValueError) as exc:
            self.querytool._entity_type('sometype:somename:something')
        assert exc.value[0] == 'too many values to unpack'

    def test_run(self):
        self.querytool._load_config = mock.Mock()
        self.querytool._query_membership = mock.Mock()
        self.querytool.args.action = 'member'
        self.querytool.run()
        self.querytool._load_config.assert_called_with()
        self.querytool._query_membership.assert_called_with()

    @log_capture()
    @mock.patch('%s.IntegrityChecker' % modulename)
    @mock.patch('%s.ConfigLoader' % modulename)
    def test_load_config(self, mock_loader, mock_checker, log):
        self.querytool._load_config()
        mock_loader.assert_called_with(
            self.querytool.args.config, self.querytool.settings)
        mock_load = mock_loader.return_value.load
        mock_load.assert_called_with()
        assert self.querytool.entities == mock_load.return_value
        mock_checker.assert_called_with(
            self.querytool.entities, self.querytool.settings)
        mock_checker.return_value.check.assert_called_with()
        log.check(
            ('QueryTool', 'INFO', 'Running pre-query config load & checks'),
            ('QueryTool', 'INFO', 'Pre-query config load & checks finished'))

    def test_resolve_entities(self):
        self.querytool._load_config()
        entity_list = [('user', 'firstname.lastname'), ('group', 'group-two')]
        result = self.querytool._resolve_entities(entity_list)
        assert len(result) == 2
        assert isinstance(result[0], entities.FreeIPAUser)
        assert result[0].name == 'firstname.lastname'
        assert isinstance(result[1], entities.FreeIPAUserGroup)
        assert result[1].name == 'group-two'

    @log_capture()
    def test_build_graph(self, log):
        self.querytool.graph = {}
        self.querytool.predecessors = {}
        entity = self.querytool.entities['user']['firstname.lastname']
        assert [repr(i) for i in self.querytool._build_graph(entity)] == [
            'group group-one-users', 'group group-two',
            'group group-three-users']
        assert dict((repr(k), map(repr, v))
                    for k, v in self.querytool.graph.iteritems()) == {
            'group group-one-users': ['group group-two',
                                      'group group-three-users'],
            'group group-three-users': [],
            'group group-two': ['group group-three-users'],
            'user firstname.lastname': ['group group-one-users',
                                        'group group-two',
                                        'group group-three-users']}
        assert dict((repr(k), map(repr, v))
                    for k, v in self.querytool.predecessors.iteritems()) == {
            'group group-one-users': ['user firstname.lastname'],
            'group group-three-users': ['group group-two'],
            'group group-two': ['group group-one-users']}
        log.check(('QueryTool', 'DEBUG',
                   'Calculating membership graph for firstname.lastname'),
                  ('QueryTool', 'DEBUG',
                   'Calculating membership graph for group-one-users'),
                  ('QueryTool', 'DEBUG',
                   'Calculating membership graph for group-two'),
                  ('QueryTool', 'DEBUG',
                   'Calculating membership graph for group-three-users'),
                  ('QueryTool', 'DEBUG',
                   'Found 0 target entities for group-three-users'),
                  ('QueryTool', 'DEBUG',
                   'Found 1 target entities for group-two'),
                  ('QueryTool', 'DEBUG',
                   'Found 2 target entities for group-one-users'),
                  ('QueryTool', 'DEBUG',
                   'Found 3 target entities for firstname.lastname'))

    @log_capture(level=logging.INFO)
    def test_query_membership(self, log):
        self.querytool.args.members = [('user', 'firstname.lastname2'),
                                       ('group', 'group-one-users')]
        self.querytool.args.targets = [('group', 'group-one-users'),
                                       ('group', 'group-two'),
                                       ('group', 'group-three-users')]
        self.querytool._query_membership()
        log.check(
            ('QueryTool', 'INFO',
             'firstname.lastname2 IS NOT a member of group-one-users'),
            ('QueryTool', 'INFO',
             'firstname.lastname2 IS NOT a member of group-two'),
            ('QueryTool', 'INFO',
             'firstname.lastname2 IS a member of group-three-users'),
            ('QueryTool', 'INFO',
             'group-one-users IS NOT a member of group-one-users'),
            ('QueryTool', 'INFO', 'group-one-users IS a member of group-two'),
            ('QueryTool', 'INFO',
             'group-one-users IS a member of group-three-users'))

    @log_capture()
    def test_construct_path(self):
        self.querytool.graph = {}
        self.querytool.predecessors = {}
        self.querytool.args.members = [('user', 'firstname.lastname'),
                                       ('group', 'group-one-users')]
        self.querytool.args.targets = [('group', 'group-one-users'),
                                       ('group', 'group-two'),
                                       ('group', 'group-three-users')]
        self.querytool._query_membership()
        target = self.querytool.entities['group']['group-two']
        member = self.querytool.entities['user']['firstname.lastname']
        paths = self.querytool._construct_path(target, member)
        assert len(paths) == 1
        assert map(repr, paths[0]) == [
            'user firstname.lastname', 'group group-one-users',
            'group group-two']

    @log_capture()
    def test_construct_path_non_member(self):
        self.querytool.graph = {}
        self.querytool.predecessors = {}
        self.querytool.args.members = [('user', 'firstname.lastname'),
                                       ('group', 'group-one-users')]
        self.querytool.args.targets = [('group', 'group-one-users'),
                                       ('group', 'group-two'),
                                       ('group', 'group-three-users')]
        self.querytool._query_membership()
        target = self.querytool.entities['group']['group-two']
        member = self.querytool.entities['user']['firstname.lastname2']
        assert self.querytool._construct_path(target, member) == []
