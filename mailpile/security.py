"""
Global Mailpile crypto/privacy/security policy

This module attempts to collect in one place all of the different
security related decisions made by the app, in order to facilitate
review and testing.

"""
import time

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *


##[ These are the sys.lockdown restrictions ]#################################


def _lockdown(config):
    lockdown = config.sys.lockdown or 0
    try:
        return int(lockdown)
    except ValueError:
        pass
    lockdown = lockdown.lower()
    if lockdown == 'false': return 0
    if lockdown == 'true': return 1
    if lockdown == 'demo': return -1
    if lockdown == 'strict': return 2
    return 1


def _lockdown_minimal(config):
    if _lockdown(config) != 0:
        return _('In lockdown, doing nothing.')
    return False


def _lockdown_basic(config):
    if _lockdown(config) > 0:
        return _('In lockdown, doing nothing.')
    return False


def _lockdown_strict(config):
    if _lockdown(config) > 1:
        return _('In lockdown, doing nothing.')
    return False


CC_ACCESS_FILESYSTEM  = [_lockdown_minimal]
CC_BROWSE_FILESYSTEM  = [_lockdown_basic]
CC_CHANGE_CONFIG      = [_lockdown_basic]
CC_CHANGE_CONTACTS    = [_lockdown_basic]
CC_CHANGE_GNUPG       = [_lockdown_basic]
CC_CHANGE_FILTERS     = [_lockdown_strict]
CC_CHANGE_SECURITY    = [_lockdown_minimal]
CC_CHANGE_TAGS        = [_lockdown_strict]
CC_COMPOSE_EMAIL      = [_lockdown_strict]
CC_CPU_INTENSIVE      = [_lockdown_basic]
CC_LIST_PRIVATE_DATA  = [_lockdown_minimal]
CC_TAG_EMAIL          = [_lockdown_strict]
CC_QUIT               = [_lockdown_minimal]

CC_CONFIG_MAP = {
    # These are security critical
    'homedir': CC_CHANGE_SECURITY,
    'master_key': CC_CHANGE_SECURITY,
    'sys': CC_CHANGE_SECURITY,
    'prefs.gpg_use_agent': CC_CHANGE_SECURITY,
    'prefs.gpg_recipient': CC_CHANGE_SECURITY,
    'prefs.encrypt_mail': CC_CHANGE_SECURITY,
    'prefs.encrypt_index': CC_CHANGE_SECURITY,
    'prefs.encrypt_vcards': CC_CHANGE_SECURITY,
    'prefs.encrypt_events': CC_CHANGE_SECURITY,
    'prefs.encrypt_misc': CC_CHANGE_SECURITY,

    # These access the filesystem and local OS
    'prefs.open_in_browser': CC_ACCESS_FILESYSTEM,
    'prefs.rescan_command': CC_ACCESS_FILESYSTEM,
    '*.command': CC_ACCESS_FILESYSTEM,

    # These have their own CC
    'tags': CC_CHANGE_TAGS,
    'filters': CC_CHANGE_FILTERS,
}


def forbid_command(command_obj, cc_list=None, config=None):
    """
    Determine whether to block a command or not.
    """
    if cc_list is None:
        cc_list = command_obj.COMMAND_SECURITY
    if cc_list:
        for cc in cc_list:
            forbid = cc(config or command_obj.session.config)
            if forbid:
                return forbid
    return False


def forbid_config_change(config, config_key):
    parts = config_key.split('.')
    cc_list = []
    while parts:
        cc_list += CC_CONFIG_MAP.get('.'.join(parts), [])
        cc_list += CC_CONFIG_MAP.get('*.' + parts.pop(-1), [])
    if not cc_list:
        cc_list = CC_CHANGE_CONFIG
    return forbid_command(None, cc_list=cc_list, config=config)


##[ Securely download content from the web ]##########################

def secure_urlget(session, url, data=None, timeout=30, anonymous=False):
    from mailpile.conn_brokers import Master as ConnBroker
    from urllib2 import urlopen

    if session.config.prefs.web_content not in ("on", "anon"):
        raise IOError("Web content is disabled by policy")

    if url.startswith('https:'):
        conn_need, conn_reject = [ConnBroker.OUTGOING_HTTPS], []
    else:
        conn_need, conn_reject = [ConnBroker.OUTGOING_HTTP], []

    if session.config.prefs.web_content == "anon" or anonymous:
        conn_reject += [ConnBroker.OUTGOING_TRACKABLE]

    with ConnBroker.context(need=conn_need, reject=conn_reject) as ctx:
        return urlopen(url, data=None, timeout=timeout).read()


##[ Common web-server security code ]#################################

CSRF_VALIDITY = 48 * 3600  # How long a CSRF token remains valid

def http_content_security_policy(http_server):
    """
    Calculate the default Content Security Policy string.

    This provides an important line of defense against malicious
    Javascript being injected into our web user-interface.
    """
    # FIXME: Allow deviations in config, for integration purposes
    # FIXME: Clean up Javascript and then make this more strict
    return ("default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "img-src 'self' data:")


def make_csrf_token(req, session_id, ts=None):
    """
    Generate a hashed token from the current timestamp, session ID and
    the server secret, to avoid CSRF attacks.
    """
    ts = '%x' % (ts if (ts is not None) else time.time())
    payload = [req.server.secret, session_id, ts]
    return '%s-%s' % (ts, b64w(sha512b64('-'.join(payload))))


def valid_csrf_token(req, session_id, csrf_token):
    """
    Check the validity of a CSRF token.
    """
    try:
        when = int(csrf_token.split('-')[0], 16)
        return ((when > time.time() - CSRF_VALIDITY) and
                (csrf_token == make_csrf_token(req, session_id, ts=when)))
    except (ValueError, IndexError):
        return False
