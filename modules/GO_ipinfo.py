# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:        GO_ipinfo
# Purpose:     GhostOSINT plug-in to identify the Geo-location of IP addresses
#              identified by other modules using ipinfo.io.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     17/06/2017
# Copyright:   (c) Steve Micallef 2017
# Licence:     GPL
# -------------------------------------------------------------------------------

import json

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_ipinfo(GhostOsintPlugin):

    meta = {
        'name': "IPInfo.io",
        'summary': "使用 ipinfo.io 查找IP地址的物理位置.",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Real World"],
        'dataSource': {
            'website': "https://ipinfo.io",
            'model': "FREE_AUTH_LIMITED",
            'references': [
                "https://ipinfo.io/developers"
            ],
            'apiKeyInstructions': [
                "访问 https://ipinfo.io/",
                "注册一个免费账户",
                "导航到 https://ipinfo.io/account",
                "API 密钥将在 'is your access token'"
            ],
            'favIcon': "https://ipinfo.io/static/favicon-96x96.png?v3",
            'logo': "https://ipinfo.io/static/deviceicons/android-icon-96x96.png",
            'description': "IP地址数据的受信任源.\n"
            "使用 IPinfo，你可以精确定位用户的位置、定制用户体验、防止欺诈、确保法规遵从性，等等.",
        }
    }

    # Default options
    opts = {
        "api_key": ""
    }
    optdescs = {
        "api_key": "Ipinfo.io 的 token."
    }

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()
        self.errorState = False

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return ['IP_ADDRESS', 'IPV6_ADDRESS']

    # What events this module produces
    # This is to support the end user in selecting modules based on events
    # produced.
    def producedEvents(self):
        return ["GEOINFO"]

    # https://ipinfo.io/developers
    def queryIP(self, ip):
        headers = {
            'Authorization': "Bearer " + self.opts['api_key']
        }
        res = self.GhostOsint.fetchUrl("https://ipinfo.io/" + ip + "/json",
                               timeout=self.opts['_fetchtimeout'],
                               useragent=self.opts['_useragent'],
                               headers=headers)

        if res['code'] == "429":
            self.error("You are being rate-limited by ipinfo.io.")
            self.errorState = True
            return None

        if res['content'] is None:
            self.info("No GeoIP info found for " + ip)
            return None

        try:
            return json.loads(res['content'])
        except Exception as e:
            self.debug(f"Error processing JSON response: {e}")

        return None

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        if self.errorState:
            return

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if self.opts['api_key'] == "":
            self.error("You enabled GO_ipinfo but did not set an API key!")
            self.errorState = True
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        data = self.queryIP(eventData)

        if data is None:
            return

        if 'country' not in data:
            return

        location = ', '.join([_f for _f in [data.get('city'), data.get('region'), data.get('country')] if _f])
        self.info("Found GeoIP for " + eventData + ": " + location)

        evt = GhostOsintEvent("GEOINFO", location, self.__name__, event)
        self.notifyListeners(evt)

# End of GO_ipinfo class
