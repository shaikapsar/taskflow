# -*- coding: utf-8 -*-

#    Copyright (C) 2014 Yahoo! Inc. All Rights Reserved.
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

import collections
import contextlib
import copy
import logging

from oslo.utils import reflection
import six

LOG = logging.getLogger(__name__)


class _Listener(object):
    """Internal helper that represents a notification listener/target."""

    def __init__(self, callback, args=None, kwargs=None, details_filter=None):
        self._callback = callback
        self._details_filter = details_filter
        if not args:
            self._args = ()
        else:
            self._args = args[:]
        if not kwargs:
            self._kwargs = {}
        else:
            self._kwargs = kwargs.copy()

    @property
    def kwargs(self):
        return self._kwargs

    @property
    def args(self):
        return self._args

    def __call__(self, event_type, details):
        if self._details_filter is not None:
            if not self._details_filter(details):
                return
        kwargs = self._kwargs.copy()
        kwargs['details'] = details
        self._callback(event_type, *self._args, **kwargs)

    def __repr__(self):
        repr_msg = "%s object at 0x%x calling into '%r'" % (
            reflection.get_class_name(self), id(self), self._callback)
        if self._details_filter is not None:
            repr_msg += " using details filter '%r'" % self._details_filter
        return "<%s>" % repr_msg

    def is_equivalent(self, callback, details_filter=None):
        if not reflection.is_same_callback(self._callback, callback):
            return False
        if details_filter is not None:
            if self._details_filter is None:
                return False
            else:
                return reflection.is_same_callback(self._details_filter,
                                                   details_filter)
        else:
            return self._details_filter is None

    def __eq__(self, other):
        if isinstance(other, _Listener):
            return self.is_equivalent(other._callback,
                                      details_filter=other._details_filter)
        else:
            return NotImplemented


class Notifier(object):
    """A notification helper class.

    It is intended to be used to subscribe to notifications of events
    occurring as well as allow a entity to post said notifications to any
    associated subscribers without having either entity care about how this
    notification occurs.
    """

    #: Keys that can *not* be used in callbacks arguments
    RESERVED_KEYS = ('details',)

    #: Kleene star constant that is used to recieve all notifications
    ANY = '*'

    #: Events which can *not* be used to trigger notifications
    _DISALLOWED_NOTIFICATION_EVENTS = set([ANY])

    def __init__(self):
        self._listeners = collections.defaultdict(list)

    def __len__(self):
        """Returns how many callbacks are registered."""
        count = 0
        for (_event_type, listeners) in six.iteritems(self._listeners):
            count += len(listeners)
        return count

    def is_registered(self, event_type, callback, details_filter=None):
        """Check if a callback is registered."""
        for listener in self._listeners.get(event_type, []):
            if listener.is_equivalent(callback, details_filter=details_filter):
                return True
        return False

    def reset(self):
        """Forget all previously registered callbacks."""
        self._listeners.clear()

    def notify(self, event_type, details):
        """Notify about event occurrence.

        All callbacks registered to receive notifications about given
        event type will be called. If the provided event type can not be
        used to emit notifications (this is checked via
        the :meth:`.can_be_registered` method) then it will silently be
        dropped (notification failures are not allowed to cause or
        raise exceptions).

        :param event_type: event type that occurred
        :param details: additional event details *dictionary* passed to
                        callback keyword argument with the same name.
        """
        if not self.can_trigger_notification(event_type):
            LOG.debug("Event type '%s' is not allowed to trigger"
                      " notifications", event_type)
            return
        listeners = list(self._listeners.get(self.ANY, []))
        listeners.extend(self._listeners.get(event_type, []))
        if not listeners:
            return
        if not details:
            details = {}
        for listener in listeners:
            try:
                listener(event_type, details.copy())
            except Exception:
                LOG.warn("Failure calling listener %s to notify about event"
                         " %s, details: %s", listener, event_type,
                         details, exc_info=True)

    def register(self, event_type, callback,
                 args=None, kwargs=None, details_filter=None):
        """Register a callback to be called when event of a given type occurs.

        Callback will be called with provided ``args`` and ``kwargs`` and
        when event type occurs (or on any event if ``event_type`` equals to
        :attr:`.ANY`). It will also get additional keyword argument,
        ``details``, that will hold event details provided to the
        :meth:`.notify` method (if a details filter callback is provided then
        the target callback will *only* be triggered if the details filter
        callback returns a truthy value).
        """
        if not six.callable(callback):
            raise ValueError("Event callback must be callable")
        if details_filter is not None:
            if not six.callable(details_filter):
                raise ValueError("Details filter must be callable")
        if not self.can_be_registered(event_type):
            raise ValueError("Disallowed event type '%s' can not have a"
                             " callback registered" % event_type)
        if self.is_registered(event_type, callback,
                              details_filter=details_filter):
            raise ValueError("Event callback already registered with"
                             " equivalent details filter")
        if kwargs:
            for k in self.RESERVED_KEYS:
                if k in kwargs:
                    raise KeyError("Reserved key '%s' not allowed in "
                                   "kwargs" % k)
        self._listeners[event_type].append(
            _Listener(callback,
                      args=args, kwargs=kwargs,
                      details_filter=details_filter))

    def deregister(self, event_type, callback, details_filter=None):
        """Remove a single listener bound to event ``event_type``."""
        if event_type not in self._listeners:
            return False
        for i, listener in enumerate(self._listeners.get(event_type, [])):
            if listener.is_equivalent(callback, details_filter=details_filter):
                self._listeners[event_type].pop(i)
                return True
        return False

    def deregister_event(self, event_type):
        """Remove a group of listeners bound to event ``event_type``."""
        return len(self._listeners.pop(event_type, []))

    def copy(self):
        c = copy.copy(self)
        c._listeners = collections.defaultdict(list)
        for event_type, listeners in six.iteritems(self._listeners):
            c._listeners[event_type] = listeners[:]
        return c

    def listeners_iter(self):
        """Return an iterator over the mapping of event => listeners bound."""
        for event_type, listeners in six.iteritems(self._listeners):
            if listeners:
                yield (event_type, listeners)

    def can_be_registered(self, event_type):
        """Checks if the event can be registered/subscribed to."""
        return True

    def can_trigger_notification(self, event_type):
        """Checks if the event can trigger a notification."""
        if event_type in self._DISALLOWED_NOTIFICATION_EVENTS:
            return False
        else:
            return True


class RestrictedNotifier(Notifier):
    """A notification class that restricts events registered/triggered.

    NOTE(harlowja): This class unlike :class:`.Notifier` restricts and
    disallows registering callbacks for event types that are not declared
    when constructing the notifier.
    """

    def __init__(self, watchable_events, allow_any=True):
        super(RestrictedNotifier, self).__init__()
        self._watchable_events = frozenset(watchable_events)
        self._allow_any = allow_any

    def events_iter(self):
        """Returns iterator of events that can be registered/subscribed to.

        NOTE(harlowja): does not include back the ``ANY`` event type as that
        meta-type is not a specific event but is a capture-all that does not
        imply the same meaning as specific event types.
        """
        for event_type in self._watchable_events:
            yield event_type

    def can_be_registered(self, event_type):
        """Checks if the event can be registered/subscribed to."""
        return (event_type in self._watchable_events or
                (event_type == self.ANY and self._allow_any))


@contextlib.contextmanager
def register_deregister(notifier, event_type, callback=None,
                        args=None, kwargs=None, details_filter=None):
    """Context manager that registers a callback, then deregisters on exit.

    NOTE(harlowja): if the callback is none, then this registers nothing, which
                    is different from the behavior of the ``register`` method
                    which will *not* accept none as it is not callable...
    """
    if callback is None:
        yield
    else:
        notifier.register(event_type, callback,
                          args=args, kwargs=kwargs,
                          details_filter=details_filter)
        try:
            yield
        finally:
            notifier.deregister(event_type, callback,
                                details_filter=details_filter)
