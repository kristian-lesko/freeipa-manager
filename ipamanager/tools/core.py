#!/usr/bin/env python
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: BSD-3-Clause
# Copyright © 2017-2019, GoodData Corporation. All rights reserved.
"""
FreeIPA Manager Tools - core class

Core utility class for tool classes to inherit from.
"""

import abc
import logging

from ipamanager.utils import init_logging


class FreeIPAManagerToolCore(object):
    """
    Core abstract class providing logging functionality
    and serving as a base for other modules of the app.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, args=None):
        self._parse_args(args)
        init_logging(self.args.loglevel)
        self.lg = logging.getLogger(self.__class__.__name__)

    @abc.abstractmethod
    def _parse_args(self):
        """
        Method for parsing arguments.
        Should be implemented by every tool in a way relevant to its function.
        It is expected to set the `args` attribute of the instance.
        """
