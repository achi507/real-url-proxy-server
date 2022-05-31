import argparse
import logging
import re
from abc import ABCMeta, abstractmethod
from datetime import datetime
from logging import handlers
from threading import Timer, Lock

import requests
from sanic import Blueprint
from sanic import response
from sanic import Sanic
from sanic.response import text

from bilibili import BiliBili
from douyu import DouYu
from huya import huya

app = Sanic(__name__)
blueprint = Blueprint('service')

class Logger(object):
    level_relations = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'crit': logging.CRITICAL
    }

    def __init__(self, filename=None, level='info', when='D', backCount=3, fmt='%(asctime)s - %(levelname)s: %(message)s'):
        self.logger = logging.getLogger('real-url-proxy-server')
        format_str = logging.Formatter(fmt)
        self.logger.setLevel(self.level_relations.get(level))
        sh = logging.StreamHandler()
        sh.setFormatter(format_str)
        self.logger.addHandler(sh)

        if filename is not None:
            th = handlers.TimedRotatingFileHandler(
                filename=filename, when=when, backupCount=backCount, encoding='utf-8')
            th.setFormatter(format_str)
            self.logger.addHandler(th)

log = None

class RealUrlExtractor:
    __metaclass__ = ABCMeta
    lock = Lock()

    def __init__(self, room, auto_refresh_interval):
        self.room = room
        self.real_url = None
        self.last_valid_real_url = None
        self.auto_refresh_interval = auto_refresh_interval
        self.last_refresh_time = datetime.min
        if self.auto_refresh_interval > 0:
            self.refresh_timer = Timer(self.auto_refresh_interval, self.refresh_real_url)

    def reset_refresh_timer(self, failover):
        if self.auto_refresh_interval > 0:
            self.refresh_timer.cancel()
            if failover:
                refresh_interval = self.auto_refresh_interval / 2
            else:
                refresh_interval = self.auto_refresh_interval
            self.refresh_timer = Timer(refresh_interval, self.refresh_real_url)
            self.refresh_timer.start()

    def refresh_real_url(self):
        RealUrlExtractor.lock.acquire()
        try:
            self._extract_real_url()
        except:
            pass
        RealUrlExtractor.lock.release()

    @abstractmethod
    def _extract_real_url(self):
        failover = True
        if self._is_url_valid(self.real_url):
            self.last_valid_real_url = self.real_url
            failover = False
        elif self.last_valid_real_url is not None:
            self.real_url = self.last_valid_real_url

        self.last_refresh_time = datetime.now()
        self.reset_refresh_timer(failover)
        if failover:
            log.logger.info('failed to extract real url')
        else:
            log.logger.info('extracted url: %s', self.real_url)

    @abstractmethod
    def _is_url_valid(self, url):
        return False

    def get_real_url(self, bit_rate):
        if self.real_url is None or bit_rate == 'refresh':
            self._extract_real_url()

class HuYaRealUrlExtractor(RealUrlExtractor):
    def __init__(self, room, auto_refresh_interval):
        super().__init__(room, auto_refresh_interval)
        self.huya = huya(self.room, 1463993859134, 1)
        self.cdn_index = -1
        self.last_real_urls = None
        self.last_get_real_url_time = datetime.min

    def _extract_real_url(self):
        self.huya.update_live_url_info()
        cdn_count = len(self.huya.live_url_infos)
        if self.cdn_index >= cdn_count:
            self.cdn_index = 0
        if cdn_count > 0:
            self.real_url = list(self.huya.live_url_infos.values())[self.cdn_index]['hls_url']
        else:
            self.real_url = None
        super()._extract_real_url()

    def _is_url_valid(self, url):
        return url is not None

    def get_real_url(self, bit_rate):
        super().get_real_url(bit_rate)

        if bit_rate == 'refresh':
            bit_rate = None

        if bit_rate == 'switch_cdn':
            self.cdn_index += 1

        if self.last_real_urls is None or (datetime.now() - self.last_get_real_url_time).total_seconds() > 120:
            urls = self.huya.get_real_url(bit_rate)
            self.last_real_urls = urls
            self.last_get_real_url_time = datetime.now()
        else:
            urls = self.last_real_urls

        if len(urls) > 0:
            if self.cdn_index >= len(urls):
                self.cdn_index = 0
            return urls[self.cdn_index]
        return None

    def reset_last_get_real_url_time(self):
        self.last_get_real_url_time = datetime.min

    def stream_name(self):
        return list(self.huya.live_url_infos.values())[self.cdn_index]['stream_name']

    def base_url(self):
        return list(self.huya.live_url_infos.values())[self.cdn_index]['base_url']


class DouYuRealUrlExtractor(RealUrlExtractor):
    def _extract_real_url(self):
        try:
            self.real_url = DouYu(self.room).get_real_url()
        except:
            self.real_url = 'None'
        super()._extract_real_url()

    def _is_url_valid(self, url):
        return url is not None and url != 'None'

    def get_real_url(self, bit_rate):
        super().get_real_url(bit_rate)

        if bit_rate == 'refresh':
            bit_rate = None

        if not self._is_url_valid(self.real_url):
            return None
        if bit_rate is None or len(bit_rate) == 0:
            if 'flv' in self.real_url:
                return self.real_url['flv']
            elif '2000p' in self.real_url:
                return self.real_url['2000p']
            else:
                return self.real_url['900p']
        if bit_rate in self.real_url.keys():
            return self.real_url[bit_rate]

class BilibiliRealUrlExtractor(RealUrlExtractor):
    def _extract_real_url(self):
        try:
            self.real_url = BiliBili(self.room).get_real_url()
        except:
            self.real_url = 'None'
        super()._extract_real_url()

    def _is_url_valid(self, url):
        return url is not None and url != 'None'

    def get_real_url(self, bit_rate):
        super().get_real_url(bit_rate)

        if bit_rate == 'refresh':
            bit_rate = None

        if not self._is_url_valid(self.real_url):
            return None
        if 'hls_url' in self.real_url:
            return self.real_url['hls_url']
        else:
            return self.real_url['flv_url']

crosHeaders={'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET',
            'Access-Control-Allow-Headers':'Content-Type, Content-Length, Authorization'}
processor_maps = {}
auto_refresh_interval=7200

@app.get('/<provider>/<room>/<bit_rate>')
async def serviceWithRate(request,provider,room,bit_rate):
    log.logger.info('provider: %s, room: %s, bit_rate: %s', provider, room, bit_rate)
    if provider == 'douyu':
        if provider not in processor_maps.keys():
            processor_maps[provider] = {}
        douyu_processor_map = processor_maps[provider]

        try:
            if room not in douyu_processor_map.keys():
                douyu_processor_map[room] = DouYuRealUrlExtractor(room, self.auto_refresh_interval)

            real_url = douyu_processor_map[room].get_real_url(bit_rate)
            if real_url is not None:
                return response.redirect(
                    to=real_url,
                    headers=crosHeaders,
                    status=301
                )

        except Exception as e:
            log.logger.error("Failed to extract douyu real url! Error: %s", str(e))
    elif provider == 'bilibili':
        if provider not in processor_maps.keys():
            processor_maps[provider] = {}
        bilibili_processor_map = processor_maps[provider]

        try:
            if room not in bilibili_processor_map.keys():
                bilibili_processor_map[room] = BilibiliRealUrlExtractor(room, auto_refresh_interval)

            real_url = bilibili_processor_map[room].get_real_url(bit_rate)
            if real_url is not None:
                return response.redirect(
                    to=real_url,
                    headers=crosHeaders,
                    status=301
                )
        except Exception as e:
            log.logger.error("Failed to extract bilibili real url! Error: %s", str(e))
    elif provider == 'huya':
        if provider not in processor_maps.keys():
            processor_maps[provider] = {}
        huya_processor_map = processor_maps[provider]

        try:
            if room not in huya_processor_map.keys():
                huya_processor_map[room] = HuYaRealUrlExtractor(room, auto_refresh_interval)

            real_url = huya_processor_map[room].get_real_url(bit_rate)
            if real_url is not None:
                status_code = 200
                try:
                    header = {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 '
                                      '(KHTML, like Gecko) Chrome/75.0.3770.100 Mobile Safari/537.36 '
                    }
                    resp = requests.get(url=real_url, headers=header, timeout=30)
                    status_code = resp.status_code
                    m3u8_content = resp.text
                    m3u8_content = re.sub(r'(^.*?\.ts)', huya_processor_map[room].base_url() + r'/\1', m3u8_content,
                                          flags=re.M)
                except:
                    m3u8_content = '#EXTM3U\n#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1\n' + real_url
                    huya_processor_map[room].cdn_index += 1
                if status_code == 403:
                    huya_processor_map[room].reset_last_get_real_url_time()
                return response.text(body=m3u8_content,headers=crosHeaders.update({
                    'Content-type': "application/vnd.apple.mpegurl",
                    'Content-Length': str(len(m3u8_content))
                }),status=status_code)

        except Exception as e:
            log.logger.error("Failed to proxy huya hls stream! Error: %s", str(e))
    rsp = "Not Found"
    rsp = rsp.encode("gb2312")
    return response.text(body=rsp,headers=crosHeaders.update({
                    'Content-type': "text/html; charset=gb2312",
                    'Content-Length': str(len(rsp))
                }),status=404)

@app.get('/<provider>/<roomId>')
async def service(request,provider,roomId):
    return await serviceWithRate(request,provider,roomId,None)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='A proxy server to get real url of live providers.')
    parser.add_argument('-p', '--port', type=int, required=False,default=5000, help='Binding port of HTTP server.')
    parser.add_argument('-r', '--refresh', type=int, default=7200, help='Auto refresh interval in seconds, 0 means disable auto refresh.')
    parser.add_argument('-l', '--log', type=str, default=None, help='Log file path name.')
    args = parser.parse_args()

    log = Logger(args.log)

    auto_refresh_interval=args.refresh

    port = int(args.port)

    log.logger.info('Serving HTTP on %s port %d...', "0.0.0.0", args.port)

    app.blueprint(blueprint)
    app.run(host="0.0.0.0",port=port , debug=True)

    log.logger.info('Server stopped.')
