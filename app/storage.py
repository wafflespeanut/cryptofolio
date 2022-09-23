import copy
import dbm
import json
from datetime import datetime
from threading import Lock


class Storage:
    KEY_DISTRIBUTION = b"dist"
    TIME_FORMAT = "%Y%m%d"
    KEY_SUFFIX_MOCK = b"_mock"

    def __init__(self, path):
        self.path = path
        self._d = Lock()   # global storage lock
        self._dist = None  # distribution cache

    def load_distribution(self):
        self._d.acquire()
        try:
            if not self._dist:
                with dbm.open(self.path, "c") as db:
                    if db.get(self.KEY_DISTRIBUTION) is None:
                        db[self.KEY_DISTRIBUTION] = json.dumps({})
                    self._dist = json.loads(db[self.KEY_DISTRIBUTION])
            return copy.deepcopy(self._dist)
        finally:
            self._d.release()

    def set_distribution(self, dist):
        self._d.acquire()
        try:
            self._dist = copy.deepcopy(dist)
            with dbm.open(self.path, "c") as db:
                db[self.KEY_DISTRIBUTION] = json.dumps(dist)
        finally:
            self._d.release()

    def add_purchase(self, data, mock=False):
        self._d.acquire()
        try:
            with dbm.open(self.path, "c") as db:
                key = str(int(datetime.strptime(
                    datetime.now().strftime(self.TIME_FORMAT),
                    self.TIME_FORMAT).timestamp()))
                if mock:
                    key += self.KEY_SUFFIX_MOCK.decode('utf-8')
                prev = db.get(key)
                if prev is not None:
                    for k, v in json.loads(prev).items():
                        if data.get(k) is None:
                            data[k] = [0, 0]
                        worth = data[k][0] * data[k][1] + v[0] * v[1]
                        avail = data[k][0] + v[0]
                        data[k][1] = round(worth / avail, 4)
                        data[k][0] += v[0]
                db[key] = json.dumps(data)
        finally:
            self._d.release()

    def list_purchases(self, mock=False):
        self._d.acquire()
        try:
            data = []
            with dbm.open(self.path, "c") as db:
                for k in db.keys():
                    value = json.loads(db[k])
                    if k == self.KEY_DISTRIBUTION:
                        continue
                    if mock:
                        if k.endswith(self.KEY_SUFFIX_MOCK):
                            k = k.replace(self.KEY_SUFFIX_MOCK, b"")
                        else:
                            continue
                    elif k.endswith(self.KEY_SUFFIX_MOCK):
                        continue
                    data.append([int(k), value])
            data.sort(key=lambda i: i[0])
            return data
        finally:
            self._d.release()
