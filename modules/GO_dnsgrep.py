# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        GO_dnsgrep
# Purpose:     GhostOSINT plug-in for retrieving domain names
#              from Rapid7 Sonar Project data sets using DNSGrep API.
#              - https://opendata.rapid7.com/about/
#              - https://blog.erbbysam.com/index.php/2019/02/09/dnsgrep/
#              - https://github.com/erbbysam/DNSGrep
#
# Author:      <bcoles@gmail.com>
#
# Created:     2020-03-14
# Copyright:   (c) bcoles 2020
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import urllib.error
import urllib.parse
import urllib.request

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_dnsgrep(GhostOsintPlugin):

    meta = {
        'name': "DNSGrep",
        'summary': "通过 Rapid7 Sonar 项目使用 DNSGrep API 进行 被动查询DNS.",
        'flags': [],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Passive DNS"],
        'dataSource': {
            'website': "https://opendata.rapid7.com/",
            'model': "FREE_AUTH_UNLIMITED",
            'references': [
                "https://opendata.rapid7.com/apihelp/",
                "https://www.rapid7.com/about/research"
            ],
            'apiKeyInstructions': [
                "访问 https://opendata.rapid7.com/apihelp/",
                "提交请求访问的表单",
                "获得访问权限后，导航到 https://insight.rapid7.com/platform#/apiKeyManagement",
                "创建用户密钥",
                "创建后将列出API密钥"
            ],
            'favIcon': "https://www.rapid7.com/includes/img/favicon.ico",
            'logo': "https://www.rapid7.com/includes/img/Rapid7_logo.svg",
            'description': "让研究人员和社区成员能够公开访问 Project Sonar 项目的数据，该项目进行互联网范围的调查，以深入了解全球面临的常见漏洞.",
        }
    }

    # Default options
    opts = {
        'timeout': 30,
        'dns_resolve': True
    }

    # Option descriptions
    optdescs = {
        'timeout': "查询超时（秒）.",
        'dns_resolve': "DNS解析每个已识别到的域."
    }

    results = None

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()

        for opt in userOpts.keys():
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return ["DOMAIN_NAME"]

    # What events this module produces
    def producedEvents(self):
        return ["INTERNET_NAME", "INTERNET_NAME_UNRESOLVED"]

    # Query the DNSGrep REST API
    def query(self, qry):
        params = {
            'q': '.' + qry.encode('raw_unicode_escape').decode("ascii", errors='replace')
        }

        res = self.GhostOsint.fetchUrl('https://dns.bufferover.run/dns?' + urllib.parse.urlencode(params),
                               timeout=self.opts['timeout'],
                               useragent=self.opts['_useragent'])

        if res['content'] is None:
            self.info("No results found for " + qry)
            return None

        if res['code'] != '200':
            self.debug("Error retrieving search results for " + qry)
            return None

        try:
            return json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response from DNSGrep: {e}")

        return None

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if eventData in self.results:
            return
        self.results[eventData] = True

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        data = self.query(eventData)

        if data is None:
            self.info("No DNS records found for " + eventData)
            return

        evt = GhostOsintEvent('RAW_RIR_DATA', str(data), self.__name__, event)
        self.notifyListeners(evt)

        domains = list()

        # Forward DNS A records
        fdns = data.get("FDNS_A")
        if fdns:
            for r in fdns:
                try:
                    ip, domain = r.split(',')
                except Exception:
                    continue

                domains.append(domain)

        # Reverse DNS records
        rdns = data.get("RDNS")
        if rdns:
            for r in rdns:
                try:
                    ip, domain = r.split(',')
                except Exception:
                    continue

                domains.append(domain)

        for domain in domains:
            if domain in self.results:
                continue

            if not self.getTarget().matches(domain, includeParents=True):
                continue

            evt_type = "INTERNET_NAME"

            if self.opts["dns_resolve"] and not self.GhostOsint.resolveHost(domain) and not self.GhostOsint.resolveHost6(domain):
                self.debug(f"Host {domain} could not be resolved")
                evt_type += "_UNRESOLVED"

            evt = GhostOsintEvent(evt_type, domain, self.__name__, event)
            self.notifyListeners(evt)

# End of GO_dnsgrep class
