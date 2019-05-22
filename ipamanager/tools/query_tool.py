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
    def _parse_args(self):
        common = _args_common()
        parser = argparse.ArgumentParser(description='FreeIPA Manager Query')
        actions = parser.add_subparsers(help='query action to execute')

        member = actions.add_parser('member', parents=[common])
        member.add_argument(
            '-m', '--members', nargs='+', type=self._entity_type, default=[],
            required=True, help='member entities (type:name format)')
        member.add_argument(
            '-t', '--targets', nargs='+', type=self._entity_type, default=[],
            required=True, help='target entities (type:name format)')
        member.set_defaults(action='member')

        self.args = parser.parse_args()
        if not self.args.settings:
            raise ManagerError('-s (--settings) must be provided')
        self.settings = load_settings(self.args.settings)

    def _entity_type(self, value):
        entity_type, entity_name = value.split(':')
        return entity_type, entity_name

    def run(self):
        self._load_config()
        if self.args.action == 'member':
            self._query_membership()

    def _load_config(self):
        self.lg.info('Running pre-query config load & checks')
        self.entities = ConfigLoader(self.args.config, self.settings).load()
        self.checker = IntegrityChecker(self.entities, self.settings)
        self.checker.check()
        self.lg.info('Pre-query config load & checks finished')

    def _resolve_entities(self, entity_list):
        result = []
        for entity_type, entity_name in entity_list:
            resolved = find_entity(self.entities, entity_type, entity_name)
            if not resolved:
                raise ManagerError('%s %s not found in config'
                                   % (entity_type, entity_name))
            result.append(resolved)
        return result

    def _build_graph(self, entity):
        """
        Build membership graph of member entities' nested membership.
        """
        # TODO capture membership path
        result = self.graph.get(entity, [])
        if result:
            self.lg.debug('Membership for %s already calculated', entity)
            return result
        self.lg.debug('Calculating membership graph for %s %s', entity)
        memberof = entity.data_repo.get('memberOf', {})
        for target_type, targets in memberof.iteritems():
            for target in targets:
                target_entity = find_entity(self.entities, target_type, target)
                result.append(target_entity)
                result.extend(self._build_graph(target_entity))
        self.lg.debug('Found %d target entities for %s', len(result), entity)
        self.graph[entity] = result
        return result

    def _query_membership(self):
        self.graph = {}
        members = self._resolve_entities(self.args.members)
        targets = self._resolve_entities(self.args.targets)
        for entity in members:
            memberof = self._build_graph(entity)
            for target in targets:
                if target in memberof:
                    self.lg.debug('%s IS a member of %s', entity, target)
                else:
                    self.lg.debug('%s IS NOT a member of %s', entity, target)
