# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         GO_intelx
# Purpose:      Query IntelligenceX (intelx.io) for identified IP addresses,
#               domains, e-mail addresses and phone numbers.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     28/04/2019
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import datetime
import json
import time

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_intelx(GhostOsintPlugin):

    meta = {
        'name': "IntelligenceX",
        'summary': "从 IntelligenceX 中获取目标有关的IP地址、域名、电子邮件地址和电话号码的信息.",
        'flags': ["apikey"],
        'useCases': ["Investigate", "Passive"],
        'categories': ["Search Engines"],
        'dataSource': {
            'website': "https://intelx.io/",
            'model': "FREE_AUTH_LIMITED",
            'references': [
                "https://ginseg.com/wp-content/uploads/sites/2/2019/07/Manual-Intelligence-X-API.pdf",
                "https://blog.intelx.io/2019/01/25/new-developer-tab/",
                "https://github.com/IntelligenceX/SDK"
            ],
            'apiKeyInstructions': [
                "访问 https://intelx.io/",
                "注册一个免费账户",
                "导航到 https://intelx.io/account?tab=developer",
                "API 密钥将在 'Your API details'"
            ],
            'favIcon': "https://intelx.io/favicon/favicon-32x32.png",
            'logo': "https://intelx.io/assets/img/IntelligenceX.svg",
            'description': "Intelligence X 是一家独立的欧洲技术公司，由 Peter Kleissner于2018年成立. "
            "它的任务是开发和维护搜索引擎和数据档案.\n"
            "搜索使用选择器，即特定搜索词，如电子邮件地址、域名、Url地址、IP地址、CIDR、比特币地址、IPFS哈希等.\n"
            "它在暗网、文档共享平台、whois数据、公共数据泄露等地方进行搜索.\n"
            "它保存结果的历史数据存档，类似于 Wayback 机器如何从 archive.org 存储网站恢复历史副本.",
        }
    }

    # Default options
    opts = {
        "api_key": "",
        "base_url": "2.intelx.io",
        "checkcohosts": False,
        "checkaffiliates": False,
        'netblocklookup': False,
        'maxnetblock': 24,
        'subnetlookup': False,
        'maxsubnet': 24,
        'maxage': 90
    }

    # Option descriptions
    optdescs = {
        "api_key": "IntelligenceX API 密钥.",
        "base_url": "API Url地址, 在 IntelligenceX 账户设置中提供.",
        "checkcohosts": "检查共同托管的网站?",
        "checkaffiliates": "检查关联公司?",
        'netblocklookup': "在目标的网段上查找同一目标子域或域上可能存在的主机的所有IP地址?",
        'maxnetblock': "如果查找网段，则为查找其中所有IP的最大网段的大小 (CIDR 值, 24 = /24, 16 = /16, 等等.)",
        'subnetlookup': "查找目标所属子网上的所有IP地址?",
        'maxsubnet': "如果查询子网则设置子网最大的子网划分 (CIDR 值, 24 = /24, 16 = /16, 等等.)",
        'maxage': "视为有效的结果最长期限（天）. 0 = 无限."
    }

    # Be sure to completely clear any class variables in setup()
    # or you run the risk of data persisting between scan runs.

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.errorState = False

        # Clear / reset any other class member variables here
        # or you risk them persisting between threads.

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return ["IP_ADDRESS", "AFFILIATE_IPADDR", "INTERNET_NAME", "EMAILADDR",
                "CO_HOSTED_SITE", "PHONE_NUMBER", "BITCOIN_ADDRESS"]

    # What events this module produces
    def producedEvents(self):
        return ["LEAKSITE_URL", "DARKNET_MENTION_URL",
                "INTERNET_NAME", "DOMAIN_NAME",
                "EMAILADDR", "EMAILADDR_GENERIC"]

    def query(self, qry, qtype):
        retdata = list()

        headers = {
            "User-Agent": "GhostOSINT",
            "x-key": self.opts['api_key'],
        }

        payload = {
            "term": qry,
            "buckets": [],
            "lookuplevel": 0,
            "maxresults": 100,
            "timeout": 0,
            "datefrom": "",
            "dateto": "",
            "sort": 4,
            "media": 0,
            "terminate": []
        }

        url = 'https://' + self.opts['base_url'] + '/' + qtype + '/search'
        res = self.GhostOsint.fetchUrl(url, postData=json.dumps(payload),
                               headers=headers, timeout=self.opts['_fetchtimeout'])

        if res['content'] is None:
            self.info("No IntelligenceX info found for " + qry)
            return None

        if res['code'] == "402":
            self.info("IntelligenceX credits expired.")
            self.errorState = True
            return None

        try:
            ret = json.loads(res['content'])
        except Exception as e:
            self.error(f"Error processing JSON response from IntelligenceX: {e}")
            self.errorState = True
            return None

        if ret.get('status', -1) == 0:
            # Craft API URL with the id to return results
            resulturl = f"{url}/result?id={ret['id']}"
            limit = 30
            count = 0
            status = 3  # status 3 = No results yet, keep trying. 0 = Success with results
            while status in [3, 0] and count < limit:
                if self.checkForStop():
                    return None

                res = self.GhostOsint.fetchUrl(resulturl, headers=headers)
                if res['content'] is None:
                    self.info("No IntelligenceX info found for results from " + qry)
                    return None

                if res['code'] == "402":
                    self.info("IntelligenceX credits expired.")
                    self.errorState = True
                    return None

                try:
                    ret = json.loads(res['content'])
                except Exception as e:
                    self.error("Error processing JSON response from IntelligenceX: " + str(e))
                    return None

                status = ret['status']
                count += 1

                retdata.append(ret)
                # No more results left
                if status == 1:
                    # print data in json format to manipulate as desired
                    break

                time.sleep(1)

        return retdata

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        if self.opts['api_key'] == "" or self.opts['base_url'] == "":
            self.error("You enabled GO_intelx but did not set an API key and/or base URL!")
            self.errorState = True
            return

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        if eventName.startswith("AFFILIATE") and not self.opts['checkaffiliates']:
            return

        if eventName == 'CO_HOSTED_SITE' and not self.opts['checkcohosts']:
            return

        data = self.query(eventData, "intelligent")
        if data is None:
            return

        self.info("Found IntelligenceX leak data for " + eventData)
        agelimit = int(time.time() * 1000) - (86400000 * self.opts['maxage'])
        for info in data:
            for rec in info.get("records", dict()):
                try:
                    last_seen = int(datetime.datetime.strptime(rec['added'].split(".")[0], '%Y-%m-%dT%H:%M:%S').strftime('%s')) * 1000
                    if self.opts['maxage'] > 0 and last_seen < agelimit:
                        self.debug("Record found but too old, skipping.")
                        continue

                    val = None
                    evt = None
                    if "pastes" in rec['bucket']:
                        evt = "LEAKSITE_URL"
                        val = rec['keyvalues'][0]['value']
                    if rec['bucket'].startswith("darknet."):
                        evt = "DARKNET_MENTION_URL"
                        val = rec['name']

                    if not val or not evt:
                        # Try generically extracting it
                        if "systemid" not in rec:
                            continue
                        evt = "LEAKSITE_URL"
                        val = "https://intelx.io/?did=" + rec['systemid']
                except Exception as e:
                    self.error(f"Error processing content from IntelX: {e}")
                    continue

                # Notify other modules of what you've found
                e = GhostOsintEvent(evt, val, self.__name__, event)
                self.notifyListeners(e)

        if "public.intelx.io" in self.opts['base_url'] or eventName != "INTERNET_NAME":
            return

        data = self.query(eventData, "phonebook")
        if data is None:
            return

        self.info(f"Found IntelligenceX host and email data for {eventData}")
        for info in data:
            for rec in info.get("selectors", dict()):
                try:
                    val = rec['selectorvalueh']
                    evt = None
                    if rec['selectortype'] == 1:  # Email
                        evt = "EMAILADDR"
                        if val.split("@")[0] in self.opts['_genericusers'].split(","):
                            evt = "EMAILADDR_GENERIC"
                    if rec['selectortype'] == 2:  # Domain
                        evt = "INTERNET_NAME"
                        if val == eventData:
                            continue
                    if rec['selectortype'] == 3:  # URL
                        evt = "LINKED_URL_INTERNAL"

                    if not val or not evt:
                        self.debug("Unexpected record, skipping.")
                        continue
                except Exception as e:
                    self.error(f"Error processing content from IntelX: {e}")
                    continue

                # Notify other modules of what you've found
                e = GhostOsintEvent(evt, val, self.__name__, event)
                self.notifyListeners(e)

                if evt == "INTERNET_NAME" and self.GhostOsint.isDomain(val, self.opts['_internettlds']):
                    e = GhostOsintEvent("DOMAIN_NAME", val, self.__name__, event)
                    self.notifyListeners(e)

# End of GO_intelx class
