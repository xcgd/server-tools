# -*- coding: utf-8 -*-
# Copyright 2016-2017 Versada <https://versada.eu/>
# Copyright 2018 XCG Consulting <https://www.xcg-consulting.fr/>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import StringIO

from six.moves import configparser

from odoo.service import wsgi_server
from odoo.tools import config as odoo_config
from odoo.tools.safe_eval import safe_eval

from . import const
from .logutils import LoggerNameFilter, OdooSentryHandler

_logger = logging.getLogger(__name__)
HAS_RAVEN = True
try:
    import raven
    from raven.middleware import Sentry
except ImportError:
    HAS_RAVEN = False
    _logger.debug('Cannot import "raven". Please make sure it is installed.')


def get_odoo_commit(odoo_dir):
    '''Attempts to get Odoo git commit from :param:`odoo_dir`.'''
    if not odoo_dir:
        return raven.fetch_package_version('odoo')
    try:
        return raven.fetch_git_sha(odoo_dir)
    except raven.exceptions.InvalidGitRepository:
        _logger.debug(
            u'Odoo directory: "%s" not a valid git repository', odoo_dir)


def initialize_raven(config, client_cls=None):
    '''
    Setup an instance of :class:`raven.Client`.

    :param config: Sentry configuration
    :param client: class used to instantiate the raven client.
    '''
    enabled = config.get('sentry_enabled', False)
    if not (HAS_RAVEN and enabled):
        return
    options = dict()
    odoo_release = get_odoo_commit(config.get('sentry_odoo_dir'))
    sentry_options_file = config.get('sentry_options_file')
    if sentry_options_file:
        ini_str = '[_]\n' + open(sentry_options_file, 'r').read()
        ini_fp = StringIO.StringIO(ini_str)
        config2 = configparser.RawConfigParser()
        config2.readfp(ini_fp)
        for key in config2.options('_'):
            options[key] = config2.get('_', key)
        if 'tags' in options:
            options['tags'] = safe_eval(options['tags'])
        else:
            options['tags'] = dict()
    else:
        options['release'] = odoo_release
        options['tags'] = dict()
    options['tags']['odoo'] = odoo_release

    for option in const.get_sentry_options():
        value = config.get('sentry_%s' % option.key, option.default)
        if callable(option.converter):
            value = option.converter(value)
        options[option.key] = value

    level = config.get('sentry_logging_level', const.DEFAULT_LOG_LEVEL)
    exclude_loggers = const.split_multiple(
        config.get('sentry_exclude_loggers', const.DEFAULT_EXCLUDE_LOGGERS)
    )
    if level not in const.LOG_LEVEL_MAP:
        level = const.DEFAULT_LOG_LEVEL

    client_cls = client_cls or raven.Client
    client = client_cls(**options)
    handler = OdooSentryHandler(
        config.get('sentry_include_context', True),
        client=client,
        level=const.LOG_LEVEL_MAP[level],
    )
    if exclude_loggers:
        handler.addFilter(LoggerNameFilter(
            exclude_loggers, name='sentry.logger.filter'))
    raven.conf.setup_logging(handler)
    wsgi_server.application = Sentry(
        wsgi_server.application, client=client)

    client.captureMessage('Starting Odoo Server')
    return client


sentry_client = initialize_raven(odoo_config)
