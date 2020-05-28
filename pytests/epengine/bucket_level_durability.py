from copy import deepcopy
from random import sample, choice

from BucketLib.bucket import Bucket
from cb_tools.cb_cli import CbCli
from couchbase_helper.documentgenerator import doc_generator
from couchbase_helper.durability_helper import DurabilityHelper, \
    BucketDurability
from epengine.durability_base import BucketDurabilityBase
from error_simulation.cb_error import CouchbaseError
from sdk_client3 import SDKClient
from sdk_exceptions import SDKException


class CreateBucketTests(BucketDurabilityBase):
    def setUp(self):
        super(CreateBucketTests, self).setUp()

    def tearDown(self):
        super(CreateBucketTests, self).tearDown()

    def test_create_bucket_using_cli(self):
        """
        Create Bucket with all possible durability_levels and make sure
        durability levels are honored for document CRUDs
        - Will test for all bucket types (Couchbase, Ephemeral, Memcached)
        - With all possible d_levels for bucket_durability
        - Perform doc insert for each bucket to validate the sync_writes
        """
        # Create cb_cli session object
        shell = self.vbs_in_node[self.cluster.master]["shell"]
        cb_cli = CbCli(shell)

        for d_level in self.bucket_util.get_supported_durability_levels():
            create_failed = False
            test_step = "Creating %s bucket with level %s" \
                        % (self.bucket_type, d_level)

            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            # Remove unsupported replica string in case if MC bucket
            if self.bucket_type == Bucket.Type.MEMCACHED:
                del bucket_dict[Bucket.replicaNumber]

            # Object to support performing CRUDs
            bucket_obj = Bucket(bucket_dict)

            output = cb_cli.create_bucket(bucket_dict, wait=True)
            self.get_vbucket_type_mapping(bucket_obj.name)
            if "SUCCESS: Bucket created" not in str(output):
                create_failed = True
                if d_level in self.possible_d_levels[self.bucket_type]:
                    self.log_failure("Create failed for %s bucket " 
                                     "with min_durability_level %s"
                                     % (self.bucket_type, d_level))

            self.bucket_util.print_bucket_stats()
            self.summary.add_step(test_step)

            # Perform CRUDs to validate bucket_creation with durability
            if not create_failed:
                durability_helper = DurabilityHelper(
                    self.log,
                    len(self.cluster.nodes_in_cluster),
                    durability=d_level)
                verification_dict = self.get_cb_stat_verification_dict()
                self.validate_durability_with_crud(bucket_obj, d_level,
                                                   verification_dict)
                self.summary.add_step("Validate_CRUD_operation")
                # Cbstats vbucket details validation
                failed = durability_helper.verify_vbucket_details_stats(
                    self.bucket_util.buckets[0],
                    self.cluster_util.get_kv_nodes(),
                    vbuckets=self.cluster_util.vbuckets,
                    expected_val=verification_dict)
                if failed:
                    self.log_failure(
                        "Cbstat vbucket-details validation failed")
                self.summary.add_step("Cbstat validation")

            output = cb_cli.delete_bucket(bucket_obj.name)
            if create_failed:
                if "ERROR: Bucket not found" not in str(output):
                    self.log_failure("Mismatch in bucket-delete output")
            elif "SUCCESS: Bucket deleted" not in str(output):
                self.log_failure("Mismatch in bucket-delete output")
            self.summary.add_step("Delete bucket")

    def test_create_bucket_using_rest(self):
        for d_level in self.bucket_util.get_supported_durability_levels():
            create_failed = False
            test_step = "Creating %s bucket with level %s" \
                        % (self.bucket_type, d_level)

            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            # Object to support performing CRUDs
            bucket_obj = Bucket(bucket_dict)

            try:
                self.bucket_util.create_bucket(bucket_obj,
                                               wait_for_warmup=True)
                self.get_vbucket_type_mapping(bucket_obj.name)
                if d_level not in self.possible_d_levels[self.bucket_type]:
                    self.log_failure("Create succeeded for %s bucket for "
                                     "unsupported durability %s"
                                     % (self.bucket_type, d_level))
            except Exception as rest_exception:
                create_failed = True
                self.log.info(rest_exception)

            self.bucket_util.print_bucket_stats()
            self.summary.add_step(test_step)

            # Perform CRUDs to validate bucket_creation with durability
            if not create_failed:
                durability_helper = DurabilityHelper(
                    self.log,
                    len(self.cluster.nodes_in_cluster),
                    durability=d_level)
                verification_dict = self.get_cb_stat_verification_dict()

                self.validate_durability_with_crud(bucket_obj, d_level,
                                                   verification_dict)
                self.summary.add_step("Validate CRUD operation")

                # Cbstats vbucket details validation
                failed = durability_helper.verify_vbucket_details_stats(
                    self.bucket_util.buckets[0],
                    self.cluster_util.get_kv_nodes(),
                    vbuckets=self.cluster_util.vbuckets,
                    expected_val=verification_dict)
                if failed:
                    self.log_failure(
                        "Cbstat vbucket-details validation failed")
                self.summary.add_step("Cbstat validation")

            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Bucket deletion")


class BucketDurabilityTests(BucketDurabilityBase):
    def setUp(self):
        super(BucketDurabilityTests, self).setUp()

    def tearDown(self):
        super(BucketDurabilityTests, self).tearDown()

    def test_durability_with_bucket_level_none(self):
        """
        Create Buckets with NONE durability level.
        Attempts sync_write with different durability_levels and validate
        CRUDs are honored with respective durability_levels set from clients
        """

        create_desc = "Creating %s bucket with level 'None'" % self.bucket_type

        b_durability = Bucket.DurabilityLevel.NONE
        verification_dict = self.get_cb_stat_verification_dict()
        bucket_dict = self.get_bucket_dict(self.bucket_type, b_durability)

        self.log.info(create_desc)
        # Object to support performing CRUDs and create Bucket
        bucket_obj = Bucket(bucket_dict)
        self.bucket_util.create_bucket(bucket_obj,
                                       wait_for_warmup=True)
        self.get_vbucket_type_mapping(bucket_obj.name)
        self.summary.add_step(create_desc)

        # Index for doc_gen to avoid creating/deleting same docs across d_level
        index = 0
        for d_level in self.bucket_util.get_supported_durability_levels():
            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=d_level)

            self.validate_durability_with_crud(bucket_obj, b_durability,
                                               verification_dict,
                                               doc_durability=d_level,
                                               doc_start_index=index)
            self.summary.add_step("CRUD with doc_durability %s" % d_level)

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")
            index += 10
            self.summary.add_step("Cbstat vbucket-details verification")

    def test_ops_only_with_bucket_level_durability(self):
        """
        Create Buckets with durability_levels set and perform
        CRUDs from client without explicitly setting the durability and
        validate the ops to make sure respective durability is honored
        """
        for d_level in self.bucket_util.get_supported_durability_levels():
            # Avoid creating bucket with durability=None
            if d_level == Bucket.DurabilityLevel.NONE:
                continue

            verification_dict = self.get_cb_stat_verification_dict()
            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=d_level)

            step_desc = "Creating %s bucket with level '%s'" \
                        % (self.bucket_type, d_level)
            self.log.info(step_desc)

            # Object to support performing CRUDs and create Bucket
            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj,
                                           wait_for_warmup=True)
            self.get_vbucket_type_mapping(bucket_obj.name)
            self.summary.add_step(step_desc)

            self.validate_durability_with_crud(bucket_obj, d_level,
                                               verification_dict)
            self.summary.add_step("Async write with bucket durability %s"
                                  % d_level)

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")

            # Delete the bucket on server
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete %s bucket" % self.bucket_type)

    def test_higher_durability_level_from_client(self):
        """
        Create bucket with durability_levels set and perform CRUDs using
        durability_level > the bucket's durability_level and validate
        """
        d_level_order_len = len(self.d_level_order)
        for d_level in self.bucket_util.get_supported_durability_levels():
            create_desc = "Creating %s bucket with level '%s'" \
                          % (self.bucket_type, d_level)
            verification_dict = self.get_cb_stat_verification_dict()
            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=d_level)

            self.log.info(create_desc)
            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            # Object to support performing CRUDs and create Bucket
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj,
                                           wait_for_warmup=True)
            self.get_vbucket_type_mapping(bucket_obj.name)
            self.summary.add_step(create_desc)

            # Perform doc_ops using all possible higher durability levels
            index = 0
            op_type = "create"
            durability_index = self.d_level_order.index(d_level) + 1
            while durability_index < d_level_order_len:
                self.validate_durability_with_crud(
                    bucket_obj,
                    d_level,
                    verification_dict,
                    op_type=op_type,
                    doc_durability=self.d_level_order[durability_index],
                    doc_start_index=index)

                self.summary.add_step("%s with doc_level_durability %s"
                                      % (op_type,
                                         self.d_level_order[durability_index]))
                durability_index += 1
                index += 10

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")
            self.summary.add_step("Cbstat verification")

            # Delete the bucket on server
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete %s bucket" % self.bucket_type)

    def test_lower_durability_level_from_client(self):
        """
        Create bucket with durability_levels set and perform CRUDs using
        durability_level > the bucket's d_level and validate
        """
        for d_level in self.bucket_util.get_supported_durability_levels():
            create_desc = "Creating %s bucket with level '%s'" \
                          % (self.bucket_type, d_level)

            verification_dict = self.get_cb_stat_verification_dict()
            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=d_level)

            self.log.info(create_desc)
            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            # Object to support performing CRUDs and create Bucket
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj,
                                           wait_for_warmup=True)
            self.get_vbucket_type_mapping(bucket_obj.name)
            self.summary.add_step(create_desc)

            # Perform doc_ops using all possible higher durability levels
            index = 0
            op_type = "create"
            durability_index = self.d_level_order.index(d_level) - 1
            while durability_index >= 0:
                self.validate_durability_with_crud(
                    bucket_obj,
                    d_level,
                    verification_dict,
                    op_type=op_type,
                    doc_durability=self.d_level_order[durability_index],
                    doc_start_index=index)

                self.summary.add_step("%s with doc_level_durability %s"
                                      % (op_type,
                                         self.d_level_order[durability_index]))
                durability_index -= 1
                index += 10

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")
            self.summary.add_step("Cbstat verification")

            # Delete the bucket on server
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete %s bucket" % self.bucket_type)

    def test_update_durability_level(self):
        """
        Create buckets with None durability levels and perform doc_ops.
        Update bucket_durability using diag-eval with/without doc_ops in
        parallel and validate the doc_ops results.
        """
        update_during_ops = self.input.param("update_during_ops", False)
        supported_d_levels = self.bucket_util.get_supported_durability_levels()
        supported_bucket_d_levels = self.possible_d_levels[self.bucket_type]
        create_gen_1 = doc_generator(self.key, 0, self.num_items)
        create_gen_2 = doc_generator("random", self.num_items,
                                     self.num_items*2)
        update_gen = doc_generator(self.key, 0, self.num_items/2)
        delete_gen = doc_generator(self.key, self.num_items/2, self.num_items)
        # Override sdk_timeout to max value to avoid TimeoutExceptions
        self.sdk_timeout = 60

        for bucket_durability in sample(supported_bucket_d_levels,
                                        len(supported_bucket_d_levels)):
            b_durability_to_update = list(set(supported_bucket_d_levels)
                                          - set(bucket_durability))
            create_desc = "Create %s bucket with durability level '%s'" \
                          % (self.bucket_type, bucket_durability)

            self.log.info(create_desc)
            bucket_dict = self.get_bucket_dict(self.bucket_type,
                                               bucket_durability)

            # Object to support performing CRUDs and create Bucket
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj,
                                           wait_for_warmup=True)
            self.get_vbucket_type_mapping(bucket_obj.name)
            self.summary.add_step(create_desc)

            self.bucket_util.print_bucket_stats()

            # Load basic docs to support other CRUDs
            self.log.info("Performing initial doc_load")
            create_task = self.task.async_load_gen_docs(
                self.cluster, bucket_obj, create_gen_1, "create",
                exp=self.maxttl,
                compression=self.sdk_compression,
                timeout_secs=self.sdk_timeout,
                process_concurrency=8,
                batch_size=200)
            self.task_manager.get_task_result(create_task)
            if create_task.fail:
                self.log_failure("Failures seen during initial creates")
            self.summary.add_step("Initial doc_loading")

            # Initiate CRUD task objects
            create_task = self.task.async_load_gen_docs(
                self.cluster, bucket_obj, create_gen_2, "create",
                exp=self.maxttl,
                durability=choice(supported_d_levels),
                compression=self.sdk_compression,
                timeout_secs=self.sdk_timeout,
                process_concurrency=2,
                batch_size=100,
                start_task=False,
                print_ops_rate=False)
            update_task = self.task.async_load_gen_docs(
                self.cluster, bucket_obj, update_gen, "update",
                exp=self.maxttl,
                durability=choice(supported_d_levels),
                compression=self.sdk_compression,
                timeout_secs=self.sdk_timeout,
                process_concurrency=2,
                batch_size=100,
                start_task=False,
                print_ops_rate=False)
            read_task = self.task.async_load_gen_docs(
                self.cluster, bucket_obj, update_gen, "read",
                compression=self.sdk_compression,
                timeout_secs=self.sdk_timeout,
                process_concurrency=2,
                batch_size=100,
                start_task=False,
                print_ops_rate=False)
            delete_task = self.task.async_load_gen_docs(
                self.cluster, bucket_obj, delete_gen, "delete",
                exp=self.maxttl,
                durability=choice(supported_d_levels),
                compression=self.sdk_compression,
                timeout_secs=self.sdk_timeout,
                process_concurrency=2,
                batch_size=100,
                start_task=False,
                print_ops_rate=False)

            # Start CRUD and update bucket-durability as specified
            # by config param 'update_during_ops'
            for task in [create_task, update_task,
                         read_task, delete_task]:
                new_d_level = BucketDurability[b_durability_to_update.pop()]

                # Work around for MB-39608
                level_to_set = new_d_level
                if new_d_level == "majorityAndPersistActive":
                    level_to_set = "majority_and_persist_on_master"
                elif new_d_level == "persistToMajority":
                    level_to_set = "persist_to_majority"

                self.log.info("Starting %s task" % task.op_type)
                self.task_manager.add_new_task(task)

                if update_during_ops:
                    self.sleep(5, "Wait for load_task to start before "
                                  "setting durability=%s" % new_d_level)
                    # Using cbepctl with doc_ops since restart memcached
                    # is not possible with doc_ops for diag_eval update
                    self.bucket_util.update_bucket_property(
                        bucket_obj,
                        bucket_durability=new_d_level)
                else:
                    self.task_manager.get_task_result(task)

                    # Wait for queues to get drained before diag-eval restart
                    self.bucket_util._wait_for_stats_all_buckets()

                    # Using diag_eval - we can restart memcached
                    # since no doc_ops is running in background
                    self.bucket_util.update_bucket_props(
                        "durability_min_level",
                        level_to_set,
                        [bucket_obj])

                buckets = self.bucket_util.get_all_buckets()
                if buckets[0].durability_level != new_d_level:
                    self.log_failure("Failed to update bucket_d_level to %s"
                                     % new_d_level)
                self.summary.add_step("Set bucket-durability=%s"
                                      % level_to_set)

                self.bucket_util.print_bucket_stats()

                if update_during_ops:
                    self.task_manager.get_task_result(task)

                if task.fail:
                    self.log_failure("Failures seen during %s"
                                     % task.op_type)
                self.summary.add_step("Doc op %s during bucket durability"
                                      % task.op_type)

            # Delete the bucket on server
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete %s bucket" % self.bucket_type)

    def test_update_durability_between_doc_op(self):
        """
        1. Create Bucket with durability level set.
        2. Bring down a node such that durability CRUD will wait
        3. Perform doc_op and update bucket_level_durability
        4. Revert scenario induced in step#2, such that doc_op will complete
        5. Make sure doc_ops in step#3 went through using prev. d-level
        """
        # Starting from max_durability levels because to iterate
        # all lower levels for doc_ops with level update
        supported_d_levels = deepcopy(self.d_level_order)
        supported_d_levels.reverse()
        supported_d_levels += [supported_d_levels[0]]

        create_desc = "Creating %s bucket with level '%s'" \
                      % (self.bucket_type, supported_d_levels[0])

        self.log.info(create_desc)
        bucket_dict = self.get_bucket_dict(self.bucket_type,
                                           supported_d_levels[0])
        # Object to support performing CRUDs and create Bucket
        bucket_obj = Bucket(bucket_dict)
        self.bucket_util.create_bucket(bucket_obj,
                                       wait_for_warmup=True)
        self.get_vbucket_type_mapping(bucket_obj.name)
        self.summary.add_step(create_desc)

        self.bucket_util.print_bucket_stats()

        # Loop to update all other durability levels
        prev_d_level = supported_d_levels[0]
        for bucket_durability in supported_d_levels[1:]:
            target_vb_type, simulate_error = \
                self.get_vb_and_error_type(bucket_durability)

            # Pick a random node to perform error sim and load
            random_node = choice(self.vbs_in_node.keys())
            error_sim = CouchbaseError(
                self.log,
                self.vbs_in_node[random_node]["shell"])

            target_vbs = self.vbs_in_node[random_node][target_vb_type]
            doc_gen = doc_generator(self.key, 0, 1,
                                    target_vbucket=target_vbs)

            doc_load_task = self.task.async_load_gen_docs(
                self.cluster, bucket_obj, doc_gen, "update",
                durability=Bucket.DurabilityLevel.NONE,
                timeout_secs=60,
                start_task=False)

            # Simulate target error condition
            error_sim.create(simulate_error)
            self.sleep(5, "Wait before starting doc_op")
            self.task_manager.add_new_task(doc_load_task)

            new_d_level = BucketDurability[bucket_durability]
            self.sleep(5, "Wait before updating bucket level "
                          "durability=%s" % new_d_level)

            self.bucket_util.update_bucket_property(
                bucket_obj,
                bucket_durability=new_d_level)
            self.bucket_util.print_bucket_stats()

            buckets = self.bucket_util.get_all_buckets()
            if buckets[0].durability_level != new_d_level:
                self.log_failure("Failed to update bucket_d_level to %s"
                                 % new_d_level)
            self.summary.add_step("Set bucket-durability=%s" % new_d_level)

            if prev_d_level == Bucket.DurabilityLevel.NONE:
                if not doc_load_task.completed:
                    self.log_failure("Doc-op still pending for d_level 'NONE'")
            elif doc_load_task.completed:
                self.log_failure("Doc-op completed before reverting the "
                                 "error condition: %s" % simulate_error)

            # Revert the induced error condition
            error_sim.revert(simulate_error)

            self.task_manager.get_task_result(doc_load_task)
            if doc_load_task.fail:
                self.log_failure("Doc_op failed")
            self.summary.add_step("Doc_op with previous d_level %s"
                                  % prev_d_level)
            prev_d_level = bucket_durability

        # Delete the bucket on server
        self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
        self.summary.add_step("Delete %s bucket" % self.bucket_type)

    def test_sync_write_in_progress(self):
        """
        Test to simulate sync_write_in_progress error and validate the behavior
        This will validate failure in majority of nodes, where durability will
        surely fail for all CRUDs

        1. Select nodes to simulate the error which will affect the durability
        2. Enable the specified error_scenario on the selected nodes
        3. Perform individual CRUDs and verify sync_write_in_progress errors
        4. Validate the end results
        """

        def test_scenario(bucket, doc_ops,
                          with_sync_write_val=None):
            # Set crud_batch_size
            crud_batch_size = 4
            simulate_error = CouchbaseError.STOP_MEMCACHED

            # Fetch target_vbs for CRUDs
            node_vb_info = self.vbs_in_node
            target_vbuckets = node_vb_info[target_nodes[0]]["replica"]
            if len(target_nodes) > 1:
                index = 1
                while index < len(target_nodes):
                    target_vbuckets = list(
                        set(target_vbuckets).intersection(
                            set(node_vb_info[target_nodes[index]]["replica"]))
                    )
                    index += 1

            # Variable to hold one of the doc_generator objects
            gen_loader_1 = None
            gen_loader_2 = None

            # Initialize doc_generators to use for testing
            self.log.info("Creating doc_generators")
            gen_create = doc_generator(
                self.key, self.num_items, crud_batch_size,
                vbuckets=self.cluster_util.vbuckets,
                target_vbucket=target_vbuckets)
            gen_update = doc_generator(
                self.key, 0, crud_batch_size,
                vbuckets=self.cluster_util.vbuckets,
                target_vbucket=target_vbuckets, mutate=1)
            gen_delete = doc_generator(
                self.key, 0, crud_batch_size,
                vbuckets=self.cluster_util.vbuckets,
                target_vbucket=target_vbuckets)
            self.log.info("Done creating doc_generators")

            # Start CRUD operation based on the given 'doc_op' type
            if doc_ops[0] == "create":
                self.num_items += crud_batch_size
                gen_loader_1 = gen_create
            elif doc_ops[0] in ["update", "replace", "touch"]:
                gen_loader_1 = gen_update
            elif doc_ops[0] == "delete":
                gen_loader_1 = gen_delete
                self.num_items -= crud_batch_size

            if doc_ops[1] == "create":
                gen_loader_2 = gen_create
            elif doc_ops[1] in ["update", "replace", "touch"]:
                gen_loader_2 = gen_update
            elif doc_ops[1] == "delete":
                gen_loader_2 = gen_delete

            # Load required docs for doc_op_1 in case of type != create
            if doc_op[2] == "load_initial_docs":
                doc_loading_task = self.task.async_load_gen_docs(
                    self.cluster, bucket, gen_loader_1, "create", 0,
                    batch_size=crud_batch_size, process_concurrency=1,
                    timeout_secs=10,
                    print_ops_rate=False)
                self.task_manager.get_task_result(doc_loading_task)
                if doc_loading_task.fail:
                    self.log_failure("Failure while loading initial docs")
                self.summary.add_step("Create docs for %s" % doc_op[0])
                verification_dict["ops_create"] += crud_batch_size
                verification_dict["sync_write_committed_count"] \
                    += crud_batch_size

            # Initialize tasks and store the task objects
            doc_loader_task = self.task.async_load_gen_docs(
                self.cluster, bucket, gen_loader_1, doc_ops[0], 0,
                batch_size=crud_batch_size, process_concurrency=8,
                timeout_secs=60,
                print_ops_rate=False,
                start_task=False)

            # SDK client for performing individual ops
            client = SDKClient([self.cluster.master], bucket)

            # Perform specified action
            for node in target_nodes:
                error_sim = CouchbaseError(self.log,
                                           self.vbs_in_node[node]["shell"])
                error_sim.create(simulate_error,
                                 bucket_name=bucket.name)
            self.sleep(5, "Wait for error simulation to take effect")

            self.task_manager.add_new_task(doc_loader_task)
            self.sleep(5, "Wait for task_1 CRUDs to reach server")

            # Perform specified CRUD operation on sync_write docs
            tem_gen = deepcopy(gen_loader_2)
            while tem_gen.has_next():
                key, value = tem_gen.next()
                for fail_fast in [True, False]:
                    if with_sync_write_val:
                        fail = client.crud(doc_ops[1], key, value=value,
                                           exp=0,
                                           durability=with_sync_write_val,
                                           timeout=3, time_unit="seconds",
                                           fail_fast=fail_fast)
                    else:
                        fail = client.crud(doc_ops[1], key, value=value,
                                           exp=0,
                                           timeout=3, time_unit="seconds",
                                           fail_fast=fail_fast)

                    expected_exception = SDKException.AmbiguousTimeoutException
                    retry_reason = \
                        SDKException.RetryReason.KV_SYNC_WRITE_IN_PROGRESS
                    if fail_fast:
                        expected_exception = \
                            SDKException.RequestCanceledException
                        retry_reason = \
                            SDKException.RetryReason \
                            .KV_SYNC_WRITE_IN_PROGRESS_NO_MORE_RETRIES

                    # Validate the returned error from the SDK
                    if expected_exception not in str(fail["error"]):
                        self.log_failure("Invalid exception for {0}: {1}"
                                         .format(key, fail["error"]))
                    if retry_reason not in str(fail["error"]):
                        self.log_failure("Invalid retry reason for {0}: {1}"
                                         .format(key, fail["error"]))

                    # Try reading the value in SyncWrite in-progress state
                    fail = client.crud("read", key)
                    if doc_ops[0] == "create":
                        # Expected KeyNotFound in case of CREATE operation
                        if fail["status"] is True:
                            self.log_failure(
                                "%s returned value during SyncWrite state: %s"
                                % (key, fail))
                    else:
                        # Expects prev value in case of other operations
                        if fail["status"] is False:
                            self.log_failure(
                                "Key %s read failed for previous value: %s"
                                % (key, fail))

            # Revert the introduced error condition
            for node in target_nodes:
                error_sim = CouchbaseError(self.log,
                                           self.vbs_in_node[node]["shell"])
                error_sim.revert(simulate_error,
                                 bucket_name=bucket.name)

            # Wait for doc_loader_task to complete
            self.task.jython_task_manager.get_task_result(doc_loader_task)

            verification_dict["ops_%s" % doc_op[0]] += crud_batch_size
            verification_dict["sync_write_committed_count"] \
                += crud_batch_size

            # Cannot retry for CREATE/DELETE operation. So only for UPDATE
            # if doc_ops[0] == "update":
            #     # Retry doc_op after reverting the induced error
            #     while gen_loader_2.has_next():
            #         key, value = gen_loader_2.next()
            #         if with_sync_write_val:
            #             fail = client.crud(doc_ops[0], key,
            #                                value=value, exp=0,
            #                                durability=with_sync_write_val,
            #                                timeout=self.sdk_timeout,
            #                                time_unit="seconds")
            #         else:
            #             fail = client.crud(doc_ops[0], key,
            #                                value=value, exp=0)
            #         if fail["error"] or fail["status"] is False:
            #             self.log_failure(
            #                 "CRUD failed without error condition: {0}"
            #                 .format(fail))

            # Disconnect the client
            client.close()

            # Verify initial doc load count
            # self.bucket_util._wait_for_stats_all_buckets()
            # self.bucket_util.verify_stats_all_buckets(crud_batch_size)

        crud_variations = [
            ["create", "create", ""],

            ["update", "update", "load_initial_docs"],
            ["update", "delete", ""],
            ["update", "touch", ""],
            ["update", "replace", ""],

            ["delete", "delete", ""],
            ["delete", "update", "load_initial_docs"],
            ["delete", "touch", "load_initial_docs"],
            ["delete", "replace", "load_initial_docs"]
        ]

        # Select nodes to affect and open required shell_connections
        target_nodes = self.getTargetNodes()

        for b_d_level in self.possible_d_levels[self.bucket_type]:
            # Skip of Bucket durability level 'None'
            if b_d_level == Bucket.DurabilityLevel.NONE:
                continue

            verification_dict = self.get_cb_stat_verification_dict()
            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=b_d_level)

            create_desc = "Creating %s bucket with level '%s'" \
                          % (self.bucket_type, b_d_level)
            self.log.info(create_desc)
            bucket_dict = self.get_bucket_dict(self.bucket_type, b_d_level)

            # Object to support performing CRUDs and create Bucket
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj,
                                           wait_for_warmup=True)
            self.get_vbucket_type_mapping(bucket_obj.name)
            self.summary.add_step(create_desc)

            for doc_op in crud_variations:
                test_scenario(bucket_obj, doc_op)
                self.summary.add_step("SyncWriteInProgress for [%s, %s]"
                                      % (doc_op[0], doc_op[1]))

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")
            self.summary.add_step("Cbstat verification")

            # Bucket deletion
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete %s bucket" % self.bucket_type)

    def test_observe_scenario(self):
        """
        Creates bucket with bucket level durability.
        Perform CRUD operations and make sure all the operations are
        done as sync_write in server.
        Note: Passing persistTo/replicateTo will test the observe scenarios
        """

        def perform_crud_ops():
            old_cas = 0
            client = SDKClient([self.cluster.master], bucket_obj)

            for op_type in ["create", "update", "read", "replace" "delete"]:
                crud_desc = "Key %s, doc_op: %s" % (key, op_type)
                self.log.info(crud_desc)
                result = client.crud(op_type, key, value,
                                     replicate_to=self.replicate_to,
                                     persist_to=self.persist_to)

                if op_type != "read":
                    if op_type != "replace":
                        dict_key = "ops_%s" % op_type
                    else:
                        dict_key = "ops_update"

                    verification_dict[dict_key] += 1
                    verification_dict["sync_write_committed_count"] += 1
                    if result["cas"] == old_cas:
                        self.log_failure("CAS didn't get updated: %s"
                                         % result["cas"])
                elif op_type == "read":
                    verification_dict["ops_get"] += 1
                    if result["cas"] != old_cas:
                        self.log_failure("CAS updated for read operation: %s"
                                         % result["cas"])

                self.summary.add_step(crud_desc)
                old_cas = result["cas"]
            client.close()

        doc_gen = doc_generator("test_key", 0, 1, mutate=0)
        key, value = doc_gen.next()

        for d_level in self.possible_d_levels[self.bucket_type]:
            if d_level == Bucket.DurabilityLevel.NONE:
                continue

            create_desc = "Create bucket with durability %s" % d_level
            self.log.info(create_desc)

            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            # Object to support performing CRUDs
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj, wait_for_warmup=True)
            self.summary.add_step(create_desc)

            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=self.durability_level)

            verification_dict = self.get_cb_stat_verification_dict()

            # Test CRUD operations
            perform_crud_ops()

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")
            self.summary.add_step("Cbstat vbucket-details verification")

            # Delete the created bucket
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete bucket with d_level %s" % d_level)

    def test_durability_impossible(self):
        """
        Create bucket with replica > num_kv_nodes.
        Perform doc insert to make sure we get TimeoutException due to
        durability_impossible from the server.
        """

        verification_dict = self.get_cb_stat_verification_dict()

        key, value = doc_generator("test_key", 0, 1).next()
        for d_level in self.possible_d_levels[self.bucket_type]:
            if d_level == Bucket.DurabilityLevel.NONE:
                continue

            bucket_dict = self.get_bucket_dict(self.bucket_type, d_level)
            # Object to support performing CRUDs
            bucket_obj = Bucket(bucket_dict)
            self.bucket_util.create_bucket(bucket_obj, wait_for_warmup=True)
            self.summary.add_step("Create bucket with durability %s"
                                  % d_level)

            durability_helper = DurabilityHelper(
                self.log,
                len(self.cluster.nodes_in_cluster),
                durability=d_level)

            client = SDKClient([self.cluster.master], bucket_obj)
            result = client.crud("create", key, value, timeout=3)
            if result["status"] is True \
                    or SDKException.DurabilityImpossibleException \
                    not in result["error"]:
                self.log_failure("Indirect sync_write succeeded "
                                 "without enough nodes")
            client.close()

            # Cbstats vbucket details validation
            failed = durability_helper.verify_vbucket_details_stats(
                self.bucket_util.buckets[0], self.cluster_util.get_kv_nodes(),
                vbuckets=self.cluster_util.vbuckets,
                expected_val=verification_dict)
            if failed:
                self.log_failure("Cbstat vbucket-details verification failed")

            self.summary.add_step("Cbstat vbucket-details verification")

            # Delete the created bucket
            self.bucket_util.delete_bucket(self.cluster.master, bucket_obj)
            self.summary.add_step("Delete bucket with d_level %s" % d_level)