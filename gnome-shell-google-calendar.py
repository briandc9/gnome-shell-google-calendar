#!/usr/bin/python 
# -*- coding: utf-8 -*-
from datetime import datetime
from time import mktime
from getpass import getpass

import gtk
import dbus
import dbus.service
import dbus.mainloop.glib
from gdata.calendar.service import CalendarService, CalendarEventQuery
import iso8601

import keyring

class Event(object):
    def __init__(self, event_id, title, start_time, end_time, allday=False):
        self.event_id = event_id
        self.title = title
        self.start_time = start_time
        self.end_time = end_time
        self.allday = allday
    
    def __repr__(self):
        return '<Event: %r>' % (self.title)

class CalendarServer(dbus.service.Object):
    busname = 'org.gnome.Shell.CalendarServer'
    object_path = '/org/gnome/Shell/CalendarServer'
    
    def __init__(self, client):
        bus = dbus.service.BusName(self.busname,
                                        bus=dbus.SessionBus(),
                                        replace_existing=True)

        super(CalendarServer, self).__init__(bus, self.object_path)
        
        self.client = client
        self.calendars = self.get_calendars()
        
        # Events indexed by (since, until)
        self.events = {}
    
    def get_calendars(self):
        feed = self.client.GetAllCalendarsFeed()
        
        calendars = []
        urls = set()
        
        print feed.title.text + ':'
        
        for calendar in feed.entry:
            title = calendar.title.text
            url = calendar.content.src
            
            if not url in urls:
                print '  ', title
                print '    ', url
                urls.add(url)
                calendars.append((title, url))
        
        return calendars
    
    def parse_time(self, timestr):
        try:
            time = datetime.strptime(timestr, '%Y-%m-%d')
            time = time.timetuple()
            allday = True
        except ValueError:
            time = iso8601.parse_date(timestr)
            time = time.timetuple()[:-1] + (-1,) # Discard tm_isdst
            allday = False
        
        timestamp = int(mktime(time))
        
        return (timestamp, allday)
    
    def update_events(self, since_date, until_date):
        print 'Update events:', since_date, 'until', until_date
        
        # Timestamps
        since = int(mktime(since_date.timetuple()))
        until = int(mktime(until_date.timetuple()))
        
        # Clear old events
        key = (since, until)
        self.events[key] = []
        
        # Get events from all calendars
        for calendar, feed_url in self.calendars:
            print 'Getting events from', calendar, '...'
            
            query = CalendarEventQuery()
            query.feed = feed_url
            query.start_min = since_date.strftime('%Y-%m-%d')
            query.start_max = until_date.strftime('%Y-%m-%d')
            feed = self.client.CalendarQuery(query)
            
            for event in feed.entry:
                event_id = event.id.text
                title = event.title.text
                
                print '  ', title
                
                for when in event.when:
                    print '    ', when.start_time, 'to', when.end_time
                    
                    allday = False
                    
                    start, allday = self.parse_time(when.start_time)
                    end, _ = self.parse_time(when.end_time)
                    
                    if (start >= since and start < until) or \
                       (start <= since and (end - 1) > since):
                        
                        e = Event(event_id, title, start, end, allday)
                        self.events[key].append(e)
                        
                    else:
                        print '!!! Outside range !!!'
        
        print '#Events:', len(self.events[key])
    
    
    @dbus.service.method('org.gnome.Shell.CalendarServer',
                         in_signature='xxb', out_signature='a(sssbxxa{sv})')
    def GetEvents(self, since, until, force_reload):
        since = int(since)
        until = int(until)
        force_reload = bool(force_reload)
        
        print "GetEvents(since=%s, until=%s, force_reload=%s)" % \
                (since, until, force_reload)
        
        since_date = datetime.fromtimestamp(since)
        until_date = datetime.fromtimestamp(until)
        #print "  since:", since_date.strftime('%Y-%m-%d')
        #print "  until:", until_date.strftime('%Y-%m-%d')
        
        key = (since, until)
        
        print 'key:', key, 'in events?', (key in self.events)
        
        if not key in self.events or force_reload:
            self.update_events(since_date, until_date)
        
        events = []
        
        for event in self.events[key]:
            #print event.title
            
            events.append(('',               # uid
                           event.title,      # summary
                           '',               # description
                           event.allday,     # allDay
                           event.start_time, # date
                           event.end_time,   # end
                           {}))              # extras
        
        print 'Returning', len(events), 'events...'
        
        return events


def login(email, password):
    client = CalendarService()
    client.email = email
    client.password = password
    client.source = 'github-gnome_shell_google_calendar-0.1'
    client.ProgrammaticLogin()
    
    return client


def login_prompt():
    print 'Please enter your Google Calendar login information.'
    print 'The email and password will be stored securely in your keyring.'
    email = raw_input('E-mail: ')
    password = getpass('Password: ')
    
    return email, password


if __name__ == '__main__':
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    
    # Get credentials
    try:
        email, password = keyring.get_credentials()
    except keyring.KeyringError:
        email, password = login_prompt()
        keyring.set_credentials(email, password)
    
    # Login
    client = None
    while not client:
        try:
            print "Logging in as '%s'..." % email
            client = login(email, password)
        except Exception as e:
            print '%s.' % e
            email, password = login_prompt()
            keyring.set_credentials(email, password)
    
    myserver = CalendarServer(client)
    gtk.main()
