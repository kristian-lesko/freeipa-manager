#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: BSD-3-Clause
# Copyright © 2017-2019, GoodData Corporation. All rights reserved.
"""
FreeIPA Manager - query tool

A tool for querying entities for various purposes, like:
- checking if user is a member of a (nested) group,
- security label checking,
- etc.
"""

import argparse
import collections
import logging
import os

from ipamanager.config_loader import ConfigLoader
from ipamanager.errors import ManagerError
from ipamanager.integrity_checker import IntegrityChecker
from ipamanager.utils import _args_common, find_entity, load_settings
from ipamanager.tools.core import FreeIPAManagerToolCore


class QueryTool(FreeIPAManagerToolCore):
    """
    A query tool for inquiry operations over entities,
    like nested membership or security label checking.
    """
    def __init__(self, config, settings, loglevel=logging.INFO):
        self.config = config
        if not settings:
            settings = os.path.join(config, 'settings_common.yaml')
        self.settings = load_settings(settings)
        super(QueryTool, self).__init__(loglevel)
        self.graph = {}
        self.predecessors = {}
        self.paths = {}

    def load(self):
        self.lg.info('Running pre-query config load & checks')
        self.entities = ConfigLoader(self.config, self.settings).load()
        self.checker = IntegrityChecker(self.entities, self.settings)
        self.checker.check()
        self.lg.info('Pre-query config load & checks finished')

    def run(self, action, *args):
        if action == 'member':
            self._query_membership(*args)

    def _resolve_entities(self, entity_list):
        result = []
        for entity_type, entity_name in entity_list:
            resolved = find_entity(self.entities, entity_type, entity_name)
            if not resolved:
                raise ManagerError('%s %s not found in config'
                                   % (entity_type, entity_name))
            result.append(resolved)
        return result

    def build_graph(self, entity):
        """
        Build membership graph of member entities' nested membership.
        """
        result = self.graph.get(entity, set())
        if result:
            self.lg.debug('Membership for %s already calculated', entity)
            return result
        self.lg.debug('Calculating membership graph for %s', entity)
        memberof = entity.data_repo.get('memberOf', {})
        for target_type, targets in memberof.iteritems():
            for target in targets:
                target_entity = find_entity(self.entities, target_type, target)
                result.add(target_entity)
                if target_entity in self.predecessors:
                    self.predecessors[target_entity].append(entity)
                else:
                    self.predecessors[target_entity] = [entity]
                result.update(self.build_graph(target_entity))
        self.lg.debug('Found %d target entities for %s', len(result), entity)
        self.graph[entity] = result
        return result

    def check_membership(self, entity, target):
        self.build_graph(entity)
        paths = self._construct_path(target, entity)
        if paths:
            self.lg.info(
                '%s IS a member of %s; possible paths: [%s]',
                entity, target, '; '.join(' -> '.join(
                    repr(e) for e in path) for path in paths))
        else:
            self.lg.info('%s IS NOT a member of %s', entity, target)
        return paths

    def _query_membership(self, members, targets):
        member_entities = self._resolve_entities(members)
        target_entities = self._resolve_entities(targets)
        for entity in member_entities:
            for target in target_entities:
                self.check_membership(entity, target)

    def _construct_path(self, target, member):
        if (member, target) in self.paths:
            self.lg.debug('Using cached paths for %s -> %s', member, target)
            return self.paths[(member, target)]
        paths = []
        queue = collections.deque([[target]])
        while queue:
            current = queue.popleft()
            preds = self.predecessors.get(current[0], [])
            for pred in preds:
                new_path = [pred] + current
                if pred == member:
                    paths.append(new_path)
                else:
                    queue.append(new_path)
        self.paths[(member, target)] = paths
        self.lg.debug('Found %d paths %s -> %s', len(paths), member, target)
        return paths


def check_membership(user, group, config, settings=None):
    querytool = QueryTool(config, settings)
    querytool.load()
    member_entity = find_entity(querytool.entities, 'user', user)
    target_entity = find_entity(querytool.entities, 'group', group)
    return bool(querytool.check_membership(member_entity, target_entity))


def list_groups(user, config, settings=None):
    querytool = QueryTool(config, settings)
    querytool.load()
    entity = find_entity(querytool.entities, 'user', user)
    querytool.build_graph(entity)
    return (i.name for i in querytool.build_graph(entity))


def _parse_args(args=None):
    common = _args_common()
    parser = argparse.ArgumentParser(description='FreeIPA Manager Query')
    actions = parser.add_subparsers(help='query action to execute')

    member = actions.add_parser('member', parents=[common])
    member.add_argument(
        '-m', '--members', nargs='+', type=_entity_type, default=[],
        required=True, help='member entities (type:name format)')
    member.add_argument(
        '-t', '--targets', nargs='+', type=_entity_type, default=[],
        required=True, help='target entities (type:name format)')
    member.set_defaults(action='member')

    args = parser.parse_args(args)
    if not args.settings:
        raise ManagerError('-s (--settings) must be provided')
    return args


def _entity_type(value):
    entity_type, entity_name = value.split(':')
    return entity_type, entity_name


def main():
    args = _parse_args()
    querytool = QueryTool(args.config, args.settings, args.loglevel)
    querytool.load()
    querytool.run(args.action, args.members, args.targets)


if __name__ == '__main__':
    main()
