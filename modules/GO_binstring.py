# coding: utf-8
# -------------------------------------------------------------------------------
# Name:         GO_binstring
# Purpose:      Identify strings in binary content.
#
# Author:      Steve Micallef <steve@binarypool.com>
#
# Created:     03/12/2016
# Copyright:   (c) Steve Micallef
# Licence:     GPL
# -------------------------------------------------------------------------------

import string

from ghostosint import GhostOsintEvent, GhostOsintPlugin


class GO_binstring(GhostOsintPlugin):

    meta = {
        'name': "二进制字符串提取器",
        'summary': "尝试识别二进制内容中的字符串.",
        'flags': ["errorprone"],
        'useCases': ["Footprint"],
        'categories': ["Content Analysis"]
    }

    # Default options
    opts = {
        'minwordsize': 5,
        'maxwords': 100,
        'maxfilesize': 1000000,
        'usedict': True,
        'fileexts': ['png', 'gif', 'jpg', 'jpeg', 'tiff', 'tif',
                     'ico', 'flv', 'mp4', 'mp3', 'avi', 'mpg',
                     'mpeg', 'dat', 'mov', 'swf', 'exe', 'bin'],
        'filterchars': '#}{|%^&*()=+,;[]~'
    }

    # Option descriptions
    optdescs = {
        'minwordsize': "在二进制文件中找到字符串时，请确保它至少具有此长度。有助于排除误报.",
        'usedict': "使用字典进一步减少误报, 找到的任何字符串都必须包含字典中的单词（对于较大的字典文件会非常慢）.",
        'fileexts': "要获取和分析的文件类型.",
        'maxfilesize': "要下载以供分析的最大的文件大小（字节）.",
        'maxwords': "找到这么多后，停止报告来自单个二进制文件的字符串.",
        'filterchars': "忽略包含这些字符的字符串，因为它们可能只是垃圾ASCII码."
    }

    results = list()
    d = None
    n = None
    fq = None

    def setup(self, sfc, userOpts=dict()):
        self.GhostOsint = sfc
        self.results = list()
        self.__dataSource__ = "Target Website"

        self.d = set(self.GhostOsint.dictwords())

        for opt in list(userOpts.keys()):
            self.opts[opt] = userOpts[opt]

    def getStrings(self, content):
        words = list()
        result = ""

        if not content:
            return None

        for c in content:
            c = str(c)
            if len(words) >= self.opts['maxwords']:
                break
            if c in string.printable and c not in string.whitespace:
                result += c
                continue
            if len(result) >= self.opts['minwordsize']:
                if self.opts['usedict']:
                    accept = False
                    for w in self.d:
                        if result.startswith(w) or result.endswith(w):
                            accept = True
                            break

                if self.opts['filterchars']:
                    accept = True
                    for x in self.opts['filterchars']:
                        if x in result:
                            accept = False
                            break

                if not self.opts['filterchars'] and not self.opts['usedict']:
                    accept = True

                if accept:
                    words.append(result)

                result = ""

        if len(words) == 0:
            return None

        return words

    # What events is this module interested in for input
    def watchedEvents(self):
        return ["LINKED_URL_INTERNAL"]

    # What events this module produces
    def producedEvents(self):
        return ["RAW_FILE_META_DATA"]

    # Handle events sent to this module
    def handleEvent(self, event):
        eventName = event.eventType
        srcModuleName = event.module
        eventData = event.data

        self.debug(f"Received event, {eventName}, from {srcModuleName}")

        if eventData in self.results:
            return

        self.results.append(eventData)

        for fileExt in self.opts['fileexts']:
            if eventData.lower().endswith(f".{fileExt.lower()}") or f".{fileExt.lower()}?" in eventData.lower():
                res = self.GhostOsint.fetchUrl(
                    eventData,
                    useragent=self.opts['_useragent'],
                    disableContentEncoding=True,
                    sizeLimit=self.opts['maxfilesize'],
                    verify=False
                )

                if not res:
                    continue

                self.debug(f"Searching {eventData} for strings")
                words = self.getStrings(res['content'])

                if words:
                    wordstr = '\n'.join(words[0:self.opts['maxwords']])
                    evt = GhostOsintEvent("RAW_FILE_META_DATA", wordstr, self.__name__, event)
                    self.notifyListeners(evt)

# End of GO_binstring class
