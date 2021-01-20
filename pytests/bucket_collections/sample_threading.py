import base64
import urllib

import requests
from timeit import default_timer
import json
import threading
from bucket_collections.collections_base import CollectionBase
import requests
import concurrent.futures


from membase.api import httplib2

START_TIME = default_timer()


class SampleThread(CollectionBase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def fetch2(self, collection):
        base_url = "http://172.23.105.215:8091/pools/default/buckets/testBucket/collections/scope1/"
        data = {}
        data['name'] = collection
        params = urllib.urlencode(data)
        username = "Administrator"
        password = "password"
        authorization = base64.encodestring('%s:%s'
                                           % (username, password)).strip("\n")
        headers =  {'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Basic %s' % authorization,
                'Connection': 'keep-alive',
                'Accept': '*/*'}
        req_time = default_timer()
        response,content = httplib2.Http(timeout=120).request(
                    base_url, "POST", params, headers)
        res_time = default_timer() - req_time
        print("res_time",res_time)



    def fetch(self, session, collection):
        base_url = "http://172.23.105.215:8091/pools/default/buckets/testBucket/collections/scope1/"
        # data = {"name":"collection"}

        data = {}
        data['name'] = collection

        # data = {{"name":"{0}"}}.format(collection)
        # data = {'name': collection}
        # data = json.dumps(data)
        headers = {'Content-type': 'application/json'}
        response = session.post(base_url, data=data, auth=("Administrator", "password"))
        elapsed = default_timer() - START_TIME
        time_completed_at = "{:5.2f}s".format(elapsed)
        print("{0:<30} {1:>20}".format(collection, time_completed_at))

        print(response.content)
        return response


    def get_data_asynchronous(self):
        base_name = "coll"
        csvs_to_fetch = []
        for i in range(0, 500):
            name = base_name + str(i)
            csvs_to_fetch.append(name)
        with requests.Session() as session:
            session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=500, pool_maxsize=500))
            print("{0:<30} {1:>20}".format("File", "Completed at"))

            # Set any session parameters here before calling `fetch`
            # For instance, if you needed to set Headers or Authentication
            # this can be done before starting the loop

            START_TIME = default_timer()
            create_threads = []
            for csv in csvs_to_fetch:
                create_thread = threading.Thread(target=self.fetch, args=[session, csv])
                create_thread.start()
                create_threads.append(create_thread)
                if len(create_threads) > 30:
                    for create_thread in create_threads:
                        create_thread.join(30)
                    create_threads = []
            for create_thread in create_threads:
                create_thread.join(30)


    def get_data_asynchronous2(self):
        base_name = "coll"
        csvs_to_fetch = []
        for i in range(0, 500):
            name = base_name + str(i)
            csvs_to_fetch.append(name)

            # Set any session parameters here before calling `fetch`
            # For instance, if you needed to set Headers or Authentication
            # this can be done before starting the loop

        START_TIME = default_timer()
        create_threads = []
        for csv in csvs_to_fetch:
            create_thread = threading.Thread(target=self.fetch2, args=[csv])
            create_thread.start()
            create_threads.append(create_thread)
            if len(create_threads) > 50:
                for create_thread in create_threads:
                    create_thread.join(30)
                create_threads = []
        for create_thread in create_threads:
            create_thread.join(30)
        time_elapsed = "{:5.2f}s".format(default_timer() - START_TIME)
        print("time elpased",time_elapsed)


    def get_data_asynchronous3(self):
        base_name = "coll"
        csvs_to_fetch = []
        for i in range(0, 500):
            name = base_name + str(i)
            csvs_to_fetch.append(name)
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = []
            with requests.Session() as session:
                for csv in csvs_to_fetch:
                    futures.append(executor.submit(self.fetch,
                                                   session,
                                                   csv))
            for future in concurrent.futures.as_completed(futures):
                if future.exception() is not None:
                    raise future.exception()


