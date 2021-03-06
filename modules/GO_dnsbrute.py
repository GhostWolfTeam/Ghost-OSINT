# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         GO_dnsbrute
# Purpose:      GhostOSINT plug-in for attempting to resolve through brute-forcing
#               common hostnames.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     06/07/2017
# Copyright:   (c) Steve Micallef 2017
# Licence:     GPL
# -------------------------------------------------------------------------------

import random
import threading
import time

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_dnsbrute(GhostOsintPlugin):

    meta = {
        'name': "DNS 枚举",
        'summary': "尝试通过暴力破解常见名称和迭代来标识主机名.",
        'flags': [],
        'useCases': ["Footprint", "Investigate"],
        'categories': ["DNS"]
    }

    # Default options
    opts = {
        "skipcommonwildcard": True,
        "domainonly": True,
        "commons": True,
        "top10000": False,
        "numbersuffix": True,
        "numbersuffixlimit": True,
        "_maxthreads": 100
    }

    # Option descriptions
    optdescs = {
        'skipcommonwildcard': "如果检测到通配符DNS，请不要使用暴力破解.",
        'domainonly': "仅尝试暴力破解域名，而不是主机名（某些主机名也是子域名）.",
        'commons': "尝试大约750个常见主机名/子域名的列表.",
        'top10000': "尝试10000个常用主机名/子域名。将使扫描变得更慢.",
        'numbersuffix': "对于找到的任何主机，请尝试追加 1, 01, 001, -1, -01, -001, 2, 02, 等等. (最多10个)",
        'numbersuffixlimit': "限制对已解析的主机使用数字后缀? 如果禁用，这将显著延长扫描的持续时间.",
        "_maxthreads": "最大线程数"
    }

    events = None
    sublist = None
    lock = None

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.sublist = self.tempStorage()
        self.events = self.tempStorage()
        self.__dataSource__ = "DNS"
        self.lock = threading.Lock()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

        dicts_dir = f"{self.GhostOsint.myPath()}/ghostosint/dicts/"
        cslines = list()
        if self.opts['commons']:
            cs = open(f"{dicts_dir}/subdomains.txt", 'r')
            cslines = cs.readlines()
            for s in cslines:
                s = s.strip()
                self.sublist[s] = True

        ttlines = list()
        if self.opts['top10000']:
            tt = open(f"{dicts_dir}/subdomains-10000.txt", 'r')
            ttlines = tt.readlines()
            for s in ttlines:
                s = s.strip()
                self.sublist[s] = True

    # What events is this module interested in for input
    def watchedEvents(self):
        ret = ['DOMAIN_NAME']
        if not self.opts['domainonly'] or self.opts['numbersuffix']:
            ret.append('INTERNET_NAME')
        return ret

    # What events this module produces
    # This is to support the end user in selecting modules based on events
    # produced.
    def producedEvents(self):
        return ["INTERNET_NAME"]

    def tryHost(self, name):
        try:
            if self.GhostOsint.resolveHost(name) or self.GhostOsint.resolveHost6(name):
                with self.lock:
                    self.hostResults[name] = True
        except Exception:
            with self.lock:
                self.hostResults[name] = False

    def tryHostWrapper(self, hostList, sourceEvent):
        self.hostResults = dict()
        running = True
        i = 0
        t = []

        # Spawn threads for scanning
        self.info("Spawning threads to check hosts: " + str(hostList))
        for name in hostList:
            tn = 'thread_GO_dnsbrute_' + str(random.SystemRandom().randint(1, 999999999))
            t.append(threading.Thread(name=tn, target=self.tryHost, args=(name,)))
            t[i].start()
            i += 1

        # Block until all threads are finished
        while running:
            found = False
            for rt in threading.enumerate():
                if rt.name.startswith("thread_GO_dnsbrute_"):
                    found = True

            if not found:
                running = False

            time.sleep(0.05)

        for res in self.hostResults:
            if self.hostResults.get(res, False):
                self.sendEvent(sourceEvent, res)

    # Store the result internally and notify listening modules
    def sendEvent(self, source, result):
        self.info("Found a brute-forced host: " + result)
        # Report the host
        evt = GhostOsintEvent("INTERNET_NAME", result, self.__name__, source)
        self.notifyListeners(evt)

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data
        eventDataHash = self.GhostOsint.hashstring(eventData)

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if srcModuleName == "GO_dnsbrute":
            return

        if eventDataHash in self.events:
            return
        self.events[eventDataHash] = True

        if eventName == "INTERNET_NAME" and not self.getTarget().matches(eventData, includeChildren=False):
            if not self.opts['numbersuffix']:
                return

            if self.checkForStop():
                return

            h, dom = eventData.split(".", 1)

            # Try resolving common names
            wildcard = self.GhostOsint.checkDnsWildcard(dom)
            if self.opts['skipcommonwildcard'] and wildcard:
                self.debug("Wildcard DNS detected on " + dom + " so skipping host iteration.")
                return

            dom = "." + dom
            nextsubs = dict()
            for i in range(10):
                nextsubs[h + str(i) + dom] = True
                nextsubs[h + "0" + str(i) + dom] = True
                nextsubs[h + "00" + str(i) + dom] = True
                nextsubs[h + "-" + str(i) + dom] = True
                nextsubs[h + "-0" + str(i) + dom] = True
                nextsubs[h + "-00" + str(i) + dom] = True

            self.tryHostWrapper(list(nextsubs.keys()), event)

            # The rest of the module is for handling targets only
            return

        # Only for the target, from this point forward...
        if not self.getTarget().matches(eventData, includeChildren=False):
            return

        # Try resolving common names
        self.debug("Iterating through possible sub-domains.")
        wildcard = self.GhostOsint.checkDnsWildcard(eventData)
        if self.opts['skipcommonwildcard'] and wildcard:
            self.debug("Wildcard DNS detected.")
            return

        targetList = list()
        for sub in self.sublist:
            if self.checkForStop():
                return

            name = sub + "." + eventData

            if len(targetList) <= self.opts['_maxthreads']:
                targetList.append(name)
            else:
                self.tryHostWrapper(targetList, event)
                targetList = list()

        # Scan whatever may be left over.
        if len(targetList) > 0:
            self.tryHostWrapper(targetList, event)

        if self.opts['numbersuffix'] and not self.opts['numbersuffixlimit']:
            nextsubs = dict()
            dom = "." + eventData
            for s in self.sublist:
                if self.checkForStop():
                    return

                for i in range(10):
                    nextsubs[s + str(i) + dom] = True
                    nextsubs[s + "0" + str(i) + dom] = True
                    nextsubs[s + "00" + str(i) + dom] = True
                    nextsubs[s + "-" + str(i) + dom] = True
                    nextsubs[s + "-0" + str(i) + dom] = True
                    nextsubs[s + "-00" + str(i) + dom] = True

                if len(list(nextsubs.keys())) >= self.opts['_maxthreads']:
                    self.tryHostWrapper(list(nextsubs.keys()), event)
                    nextsubs = dict()

            # Scan whatever may be left over.
            if len(nextsubs) > 0:
                self.tryHostWrapper(list(nextsubs.keys()), event)


# End of GO_dnsbrute class
