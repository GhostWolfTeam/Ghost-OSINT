# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        GO_mnemonic
# Purpose:     GhostOSINT plug-in for retrieving passive DNS information
#              from Mnemonic PassiveDNS API.
#
# Author:      <bcoles@gmail.com>
#
# Created:     2018-10-12
# Copyright:   (c) bcoles 2018
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_mnemonic(GhostOsintPlugin):

    meta = {
        'name': "Mnemonic 被动DNS查询",
        'summary': "从 PassiveDNS.mnemonic.no 被动获取DNS信息.",
        'flags': [],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Passive DNS"],
        'dataSource': {
            'website': "https://www.mnemonic.no",
            'model': "FREE_NOAUTH_UNLIMITED",
            'references': [
                "https://www.mnemonic.no/resources/whitepapers/",
                "https://www.mnemonic.no/research-and-development/",
                "https://docs.mnemonic.no/display/public/API/PassiveDNS+Integration+Guide"
            ],
            'favIcon': "https://www.mnemonic.no/favicon-96x96.png",
            'logo': "https://www.mnemonic.no/UI/logo.svg",
            'description': "mnemonic 帮助企业管理其安全风险，保护其数据并抵御网络威胁.\n"
            "我们由安全顾问、产品专家、威胁研究人员、事件响应人员和道德黑客组成的专家团队，"
            "结合我们的Argus安全平台，确保我们领先于先进的网络攻击，并保护我们的客户免受不断演变的威胁.",
        }
    }

    opts = {
        'per_page': 500,
        'max_pages': 2,
        'timeout': 30,
        'maxage': 180,    # 6 months
        'verify': True,
        'cohostsamedomain': False,
        'maxcohost': 100
    }

    optdescs = {
        'per_page': "每页最大结果数.",
        'max_pages': "提取结果最大页数.",
        'timeout': "查询超时（秒）.",
        'maxage': "返回的数据被视为有效的最长时间（天）.",
        'verify': "验证标识的域名是否仍解析为关联的指定IP地址.",
        'cohostsamedomain': "将同一目标域上的托管站点视为共同托管?",
        'maxcohost': "在发现这么多网站后，停止报告共同托管的网站，因为这可能表明网站是托管的.",
    }

    cohostcount = 0
    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.cohostcount = 0
        self.errorState = False

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return [
            'IP_ADDRESS',
            'IPV6_ADDRESS',
            'INTERNET_NAME',
            'DOMAIN_NAME'
        ]

    def producedEvents(self):
        return [
            'IP_ADDRESS',
            'IPV6_ADDRESS',
            'INTERNAL_IP_ADDRESS',
            'CO_HOSTED_SITE',
            'INTERNET_NAME',
            'DOMAIN_NAME'
        ]

    def query(self, qry, limit=500, offset=0):
        """Query the Mnemonic PassiveDNS v3 API.

        Args:
            qry (str): domain name or IP address
            limit (int): Limit the number of returned values.
            offset (int): Skip the initial <offset> number of values in the resultset.

        Returns:
            dict: results as JSON
        """

        params = urllib.parse.urlencode({
            'limit': limit,
            'offset': offset
        })

        res = self.GhostOsint.fetchUrl(
            f"https://api.mnemonic.no/pdns/v3/{qry}?{params}",
            timeout=self.opts['timeout'],
            useragent=self.opts['_useragent']
        )

        # Unauthenticated users are limited to 100 requests per minute, and 1000 requests per day.
        time.sleep(0.75)

        if res['content'] is None:
            self.info("No results found for " + qry)
            return None

        try:
            data = json.loads(res['content'])
        except Exception as e:
            self.debug(f"Error processing JSON response from Mnemonic: {e}")
            return None

        response_code = data.get('responseCode')

        if not response_code:
            self.debug("Error retrieving search results.")
            return None

        if response_code == 402:
            self.debug("Error retrieving search results: Resource limit exceeded")
            self.errorState = True
            return None

        if response_code != 200:
            self.debug(f"Error retrieving search results: {response_code}")
            return None

        if 'data' not in data:
            self.info(f"No results found for {qry}")
            return None

        size = data.get('size')
        count = data.get('count')

        if not count or not size:
            self.info(f"No results found for {qry}")
            return None

        self.info(f"Retrieved {size} of {count} results")

        return data['data']

    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        position = 0
        max_pages = int(self.opts['max_pages'])
        per_page = int(self.opts['per_page'])
        agelimit = int(time.time() * 1000) - (86400000 * self.opts['maxage'])
        self.cohostcount = 0
        cohosts = list()

        while position < (per_page * max_pages):
            if self.checkForStop():
                break

            if self.errorState:
                break

            data = self.query(eventData, limit=per_page, offset=position)

            if data is None:
                self.info(f"No passive DNS data found for {eventData}")
                break

            position += per_page

            for r in data:
                if "*" in r['query'] or "%" in r['query']:
                    continue

                if r['lastSeenTimestamp'] < agelimit:
                    self.debug(f"Record {r['answer']} found for {r['query']} is too old, skipping.")
                    continue

                if eventName in ['IP_ADDRESS']:
                    if r['rrtype'] == 'a':
                        if self.GhostOsint.validIP(r['query']):
                            cohosts.append(r['query'])
                    continue

                if eventName in ['INTERNET_NAME', 'DOMAIN_NAME']:
                    # Ignore PTR records
                    if r['rrtype'] == 'ptr':
                        continue

                    if r['rrtype'] == 'cname':
                        if not self.getTarget().matches(r['query'], includeParents=True):
                            continue

                        cohosts.append(r['query'])

                    if self.opts['verify']:
                        continue

                    answer = r.get('answer')

                    if r['rrtype'] == 'a':
                        if not self.GhostOsint.validIP(answer):
                            continue

                        if self.GhostOsint.isValidLocalOrLoopbackIp(answer):
                            evt = GhostOsintEvent("INTERNAL_IP_ADDRESS", answer, self.__name__, event)
                        else:
                            evt = GhostOsintEvent("IP_ADDRESS", answer, self.__name__, event)
                        self.notifyListeners(evt)

                    if r['rrtype'] == 'aaaa':
                        if not self.GhostOsint.validIP6(r['answer']):
                            continue

                        if self.GhostOsint.isValidLocalOrLoopbackIp(answer):
                            evt = GhostOsintEvent("INTERNAL_IP_ADDRESS", answer, self.__name__, event)
                        else:
                            evt = GhostOsintEvent("IPV6_ADDRESS", answer, self.__name__, event)
                        self.notifyListeners(evt)

        for co in set(cohosts):
            if self.checkForStop():
                return

            if co in self.results:
                continue

            if eventName in ["IP_ADDRESS", "IPV6_ADDRESS"]:
                if self.opts['verify'] and not self.GhostOsint.validateIP(co, eventData):
                    self.debug(f"Host {co} no longer resolves to {eventData}")
                    continue

            if self.opts['cohostsamedomain']:
                if self.cohostcount < self.opts['maxcohost']:
                    evt = GhostOsintEvent("CO_HOSTED_SITE", co, self.__name__, event)
                    self.notifyListeners(evt)
                    self.cohostcount += 1
                continue

            if self.getTarget().matches(co, includeParents=True):
                if self.opts['verify'] and not self.GhostOsint.resolveHost(co) and not self.GhostOsint.resolveHost6(co):
                    self.debug(f"Host {co} could not be resolved")
                    evt = GhostOsintEvent("INTERNET_NAME_UNRESOLVED", co, self.__name__, event)
                    self.notifyListeners(evt)
                    continue

                evt = GhostOsintEvent("INTERNET_NAME", co, self.__name__, event)
                self.notifyListeners(evt)

                if self.GhostOsint.isDomain(co, self.opts['_internettlds']):
                    evt = GhostOsintEvent("DOMAIN_NAME", co, self.__name__, event)
                    self.notifyListeners(evt)

# End of GO_mnemonic class
