# -*- coding: utf-8 -*-
'''
Return/control aspects of the grains data
'''

# Import python libs
from __future__ import print_function
import collections
import math
import operator
import os
import random
import yaml
import logging

# Import salt libs
import salt.utils
import salt.utils.dictupdate
from salt.exceptions import SaltException

__proxyenabled__ = ['*']

# Seed the grains dict so cython will build
__grains__ = {}

# Change the default outputter to make it more readable
__outputter__ = {
    'items': 'grains',
    'item': 'grains',
    'setval': 'grains',
}

# http://stackoverflow.com/a/12414913/127816
_infinitedict = lambda: collections.defaultdict(_infinitedict)

log = logging.getLogger(__name__)


def _serial_sanitizer(instr):
    '''Replaces the last 1/4 of a string with X's'''
    length = len(instr)
    index = int(math.floor(length * .75))
    return '{0}{1}'.format(instr[:index], 'X' * (length - index))


_FQDN_SANITIZER = lambda x: 'MINION.DOMAINNAME'
_HOSTNAME_SANITIZER = lambda x: 'MINION'
_DOMAINNAME_SANITIZER = lambda x: 'DOMAINNAME'


# A dictionary of grain -> function mappings for sanitizing grain output. This
# is used when the 'sanitize' flag is given.
_SANITIZERS = {
    'serialnumber': _serial_sanitizer,
    'domain': _DOMAINNAME_SANITIZER,
    'fqdn': _FQDN_SANITIZER,
    'id': _FQDN_SANITIZER,
    'host': _HOSTNAME_SANITIZER,
    'localhost': _HOSTNAME_SANITIZER,
    'nodename': _HOSTNAME_SANITIZER,
}


def get(key, default='', delimiter=':'):
    '''
    Attempt to retrieve the named value from grains, if the named value is not
    available return the passed default. The default return is an empty string.

    The value can also represent a value in a nested dict using a ":" delimiter
    for the dict. This means that if a dict in grains looks like this::

        {'pkg': {'apache': 'httpd'}}

    To retrieve the value associated with the apache key in the pkg dict this
    key can be passed::

        pkg:apache


    delimiter
        Specify an alternate delimiter to use when traversing a nested dict

        .. versionadded:: 2014.7.0

    CLI Example:

    .. code-block:: bash

        salt '*' grains.get pkg:apache
    '''
    return salt.utils.traverse_dict_and_list(__grains__,
                                             key,
                                             default,
                                             delimiter)


def has_value(key):
    '''
    Determine whether a named value exists in the grains dictionary.

    Given a grains dictionary that contains the following structure::

        {'pkg': {'apache': 'httpd'}}

    One would determine if the apache key in the pkg dict exists by::

        pkg:apache

    CLI Example:

    .. code-block:: bash

        salt '*' grains.has_value pkg:apache
    '''
    return True if salt.utils.traverse_dict_and_list(__grains__, key, False) else False


def items(sanitize=False):
    '''
    Return all of the minion's grains

    CLI Example:

    .. code-block:: bash

        salt '*' grains.items

    Sanitized CLI Example:

    .. code-block:: bash

        salt '*' grains.items sanitize=True
    '''
    if salt.utils.is_true(sanitize):
        out = dict(__grains__)
        for key, func in _SANITIZERS.items():
            if key in out:
                out[key] = func(out[key])
        return out
    else:
        return __grains__


def item(*args, **kwargs):
    '''
    Return one or more grains

    CLI Example:

    .. code-block:: bash

        salt '*' grains.item os
        salt '*' grains.item os osrelease oscodename

    Sanitized CLI Example:

    .. code-block:: bash

        salt '*' grains.item host sanitize=True
    '''
    ret = {}
    for arg in args:
        try:
            ret[arg] = __grains__[arg]
        except KeyError:
            pass
    if salt.utils.is_true(kwargs.get('sanitize')):
        for arg, func in _SANITIZERS.items():
            if arg in ret:
                ret[arg] = func(ret[arg])
    return ret


def setvals(grains, destructive=False):
    '''
    Set new grains values in the grains config file

    :param Destructive: If an operation results in a key being removed, delete the key, too. Defaults to False.

    CLI Example:

    .. code-block:: bash

        salt '*' grains.setvals "{'key1': 'val1', 'key2': 'val2'}"
    '''
    new_grains = grains
    if not isinstance(new_grains, collections.Mapping):
        raise SaltException('setvals grains must be a dictionary.')
    grains = {}
    if os.path.isfile(__opts__['conf_file']):
        gfn = os.path.join(
            os.path.dirname(__opts__['conf_file']),
            'grains'
        )
    elif os.path.isdir(__opts__['conf_file']):
        gfn = os.path.join(
            __opts__['conf_file'],
            'grains'
        )
    else:
        gfn = os.path.join(
            os.path.dirname(__opts__['conf_file']),
            'grains'
        )

    if os.path.isfile(gfn):
        with salt.utils.fopen(gfn, 'rb') as fp_:
            try:
                grains = yaml.safe_load(fp_.read())
            except Exception as e:
                return 'Unable to read existing grains file: {0}'.format(e)
        if not isinstance(grains, dict):
            grains = {}
    for key, val in new_grains.items():
        if val is None and destructive is True:
            if key in grains:
                del grains[key]
                if key in __grains__:
                    del __grains__[key]
        else:
            grains[key] = val
            __grains__[key] = val
    # Cast defaultdict to dict; is there a more central place to put this?
    yaml.representer.SafeRepresenter.add_representer(collections.defaultdict,
            yaml.representer.SafeRepresenter.represent_dict)
    cstr = yaml.safe_dump(grains, default_flow_style=False)
    try:
        with salt.utils.fopen(gfn, 'w+') as fp_:
            fp_.write(cstr)
    except (IOError, OSError):
        msg = 'Unable to write to grains file at {0}. Check permissions.'
        log.error(msg.format(gfn))
    fn_ = os.path.join(__opts__['cachedir'], 'module_refresh')
    try:
        with salt.utils.fopen(fn_, 'w+') as fp_:
            fp_.write('')
    except (IOError, OSError):
        msg = 'Unable to write to cache file {0}. Check permissions.'
        log.error(msg.format(fn_))
    # Sync the grains
    __salt__['saltutil.sync_grains']()
    # Return the grains we just set to confirm everything was OK
    return new_grains


def setval(key, val, destructive=False):
    '''
    Set a grains value in the grains config file

    :param Destructive: If an operation results in a key being removed, delete the key, too. Defaults to False.

    CLI Example:

    .. code-block:: bash

        salt '*' grains.setval key val
        salt '*' grains.setval key "{'sub-key': 'val', 'sub-key2': 'val2'}"
    '''
    return setvals({key: val}, destructive)


def append(key, val, convert=False):
    '''
    .. versionadded:: 0.17.0

    Append a value to a list in the grains config file. If the grain doesn't
    exist, the grain key is added and the value is appended to the new grain
    as a list item.

    key
        The grain key to be appended to

    val
        The value to append to the grain key

    :param convert: If convert is True, convert non-list contents into a list.
        If convert is False and the grain contains non-list contents, an error
        is given. Defaults to False.

    CLI Example:

    .. code-block:: bash

        salt '*' grains.append key val
    '''
    grains = get(key, [])
    if not isinstance(grains, list) and convert is True:
        grains = [grains]
    if not isinstance(grains, list):
        return 'The key {0} is not a valid list'.format(key)
    if val in grains:
        return 'The val {0} was already in the list {1}'.format(val, key)
    grains.append(val)
    return setval(key, grains)


def remove(key, val):
    '''
    .. versionadded:: 0.17.0

    Remove a value from a list in the grains config file

    CLI Example:

    .. code-block:: bash

        salt '*' grains.remove key val
    '''
    grains = get(key, [])
    if not isinstance(grains, list):
        return 'The key {0} is not a valid list'.format(key)
    if val not in grains:
        return 'The val {0} was not in the list {1}'.format(val, key)
    grains.remove(val)
    return setval(key, grains)


def delval(key, destructive=False):
    '''
    .. versionadded:: 0.17.0

    Delete a grain from the grains config file

    :param Destructive: Delete the key, too. Defaults to False.

    CLI Example:

    .. code-block:: bash

        salt '*' grains.delval key
    '''

    setval(key, None, destructive=destructive)


def ls():  # pylint: disable=C0103
    '''
    Return a list of all available grains

    CLI Example:

    .. code-block:: bash

        salt '*' grains.ls
    '''
    return sorted(__grains__)


def filter_by(lookup_dict, grain='os_family', merge=None, default='default'):
    '''
    .. versionadded:: 0.17.0

    Look up the given grain in a given dictionary for the current OS and return
    the result

    Although this may occasionally be useful at the CLI, the primary intent of
    this function is for use in Jinja to make short work of creating lookup
    tables for OS-specific data. For example:

    .. code-block:: jinja

        {% set apache = salt['grains.filter_by']({
            'Debian': {'pkg': 'apache2', 'srv': 'apache2'},
            'RedHat': {'pkg': 'httpd', 'srv': 'httpd'},
        }, default='Debian') %}

        myapache:
          pkg:
            - installed
            - name: {{ apache.pkg }}
          service:
            - running
            - name: {{ apache.srv }}

    Values in the lookup table may be overridden by values in Pillar. An
    example Pillar to override values in the example above could be as follows:

    .. code-block:: yaml

        apache:
          lookup:
            pkg: apache_13
            srv: apache

    The call to ``filter_by()`` would be modified as follows to reference those
    Pillar values:

    .. code-block:: jinja

        {% set apache = salt['grains.filter_by']({
            ...
        }, merge=salt['pillar.get']('apache:lookup')) %}


    :param lookup_dict: A dictionary, keyed by a grain, containing a value or
        values relevant to systems matching that grain. For example, a key
        could be the grain for an OS and the value could the name of a package
        on that particular OS.
    :param grain: The name of a grain to match with the current system's
        grains. For example, the value of the "os_family" grain for the current
        system could be used to pull values from the ``lookup_dict``
        dictionary.
    :param merge: A dictionary to merge with the ``lookup_dict`` before doing
        the lookup. This allows Pillar to override the values in the
        ``lookup_dict``. This could be useful, for example, to override the
        values for non-standard package names such as when using a different
        Python version from the default Python version provided by the OS
        (e.g., ``python26-mysql`` instead of ``python-mysql``).
    :param default: default lookup_dict's key used if the grain does not exists
         or if the grain value has no match on lookup_dict.

         .. versionadded:: 2014.1.0

    CLI Example:

    .. code-block:: bash

        salt '*' grains.filter_by '{Debian: Debheads rule, RedHat: I love my hat}'
        # this one will render {D: {E: I, G: H}, J: K}
        salt '*' grains.filter_by '{A: B, C: {D: {E: F,G: H}}}' 'xxx' '{D: {E: I},J: K}' 'C'
    '''
    ret = lookup_dict.get(
            __grains__.get(
                grain, default),
            lookup_dict.get(
                default, None)
            )

    if merge:
        if not isinstance(merge, collections.Mapping):
            raise SaltException('filter_by merge argument must be a dictionary.')

        else:

            if ret is None:
                ret = merge

            else:
                salt.utils.dictupdate.update(ret, merge)

    return ret


def _dict_from_path(path, val, delimiter=':'):
    '''
    Given a lookup string in the form of 'foo:bar:baz" return a nested
    dictionary of the appropriate depth with the final segment as a value.

    >>> _dict_from_path('foo:bar:baz', 'somevalue')
    {"foo": {"bar": {"baz": "somevalue"}}
    '''
    nested_dict = _infinitedict()
    keys = path.rsplit(delimiter)
    lastplace = reduce(operator.getitem, keys[:-1], nested_dict)
    lastplace[keys[-1]] = val

    return nested_dict


def get_or_set_hash(name,
        length=8,
        chars='abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'):
    '''
    Perform a one-time generation of a hash and write it to the local grains.
    If that grain has already been set return the value instead.

    This is useful for generating passwords or keys that are specific to a
    single minion that don't need to be stored somewhere centrally.

    State Example:

    .. code-block:: yaml

        some_mysql_user:
          mysql_user:
            - present
            - host: localhost
            - password: {{ salt['grains.get_or_set_hash']('mysql:some_mysql_user') }}

    CLI Example:

    .. code-block:: bash

        salt '*' grains.get_or_set_hash 'django:SECRET_KEY' 50
    '''
    ret = get(name, None)

    if ret is None:
        val = ''.join([random.choice(chars) for _ in range(length)])

        if ':' in name:
            name, rest = name.split(':', 1)
            val = _dict_from_path(rest, val)

        setval(name, val)

    return get(name)
