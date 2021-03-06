# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         GO_ipapicom
# Purpose:      GhostOSINT plug-in to identify the Geo-location of IP addresses
#               identified by other modules using ipapi.com
#
# Author:      Krishnasis Mandal <krishnasis@hotmail.com>
#
# Created:     29/01/2021
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import json
import time

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_ipapicom(GhostOsintPlugin):

    meta = {
        'name': "ipapi.com",
        'summary': "通过 ipapi.com API 以识别IP地址的地理位置",
        'flags': ["apikey"],
        'useCases': ["Footprint", "Investigate", "Passive"],
        'categories': ["Real World"],
        'dataSource': {
            'website': "https://ipapi.com/",
            'model': "FREE_AUTH_LIMITED",
            'references': [
                "https://ipapi.com/documentation"
            ],
            'apiKeyInstructions': [
                "访问 https://ipapi.com/",
                "注册一个免费账户",
                "浏览 https://ipapi.com/dashboard",
                "你的API密钥将列在你的API访问密钥下",
            ],
            'favIcon': "https://ipapi.com/site_images/ipapi_shortcut_icon.ico",
            'logo': "https://ipapi.com/site_images/ipapi_icon.png",
            'description': "ipapi 提供了一个易于使用的 API接口 ，允许客户查看与IPv4和IPv6地址相关的各种信息. "
            "对于处理的每个IP地址，API返回45个以上的唯一数据点，例如位置数据、连接数据、ISP信息、时区、货币和安全评估数据.",
        }
    }

    # Default options
    opts = {
        'api_key': '',
    }

    # Option descriptions
    optdescs = {
        'api_key': "ipapi.com API 密钥.",
    }

    results = None

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = self.tempStorage()

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    # What events is this module interested in for input
    def watchedEvents(self):
        return [
            "IP_ADDRESS",
            "IPV6_ADDRESS"
        ]

    # What events this module produces
    # This is to support the end user in selecting modules based on events
    # produced.
    def producedEvents(self):
        return [
            "GEOINFO",
            "RAW_RIR_DATA"
        ]

    def query(self, qry):
        queryString = f"http://api.ipapi.com/api/{qry}?access_key={self.opts['api_key']}"

        res = self.GhostOsint.fetchUrl(queryString,
                               timeout=self.opts['_fetchtimeout'],
                               useragent=self.opts['_useragent'])
        time.sleep(1.5)

        if res['code'] == "429":
            self.error("You are being rate-limited by IP-API.com.")
            self.errorState = True
            return None
        if res['content'] is None:
            self.info(f"No ipapi.com data found for {qry}")
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

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if self.errorState:
            return

        if self.opts['api_key'] == "":
            self.error("You enabled GO_ipapicom but did not set an API key!")
            self.errorState = True
            return

        if eventData in self.results:
            self.debug(f"Skipping {eventData}, already checked.")
            return

        self.results[eventData] = True

        data = self.query(eventData)
        if not data:
            return

        if data.get('country_name'):
            location = ', '.join(filter(None, [data.get('city'), data.get('region_name'), data.get('region_code'), data.get('country_name'), data.get('country_code')]))
            evt = GhostOsintEvent('GEOINFO', location, self.__name__, event)
            self.notifyListeners(evt)

            if data.get('latitude') and data.get('longitude'):
                evt = GhostOsintEvent("PHYSICAL_COORDINATES", f"{data.get('latitude')}, {data.get('longitude')}", self.__name__, event)
                self.notifyListeners(evt)

            evt = GhostOsintEvent('RAW_RIR_DATA', str(data), self.__name__, event)
            self.notifyListeners(evt)


# End of GO_ipapicom class
