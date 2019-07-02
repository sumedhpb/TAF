

package com.couchbase.test.transactions;

import com.couchbase.transactions.config.TransactionConfig;
import com.couchbase.transactions.config.TransactionConfigBuilder;
import com.couchbase.transactions.error.TransactionFailed;
import com.couchbase.transactions.log.LogDefer;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;


import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.Queue;
import java.util.stream.Collectors;
import com.couchbase.client.core.cnc.Event;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.ReactiveCollection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.transactions.AttemptContextReactive;
import com.couchbase.transactions.TransactionDurabilityLevel;
import com.couchbase.transactions.TransactionJsonDocument;
import com.couchbase.transactions.TransactionResult;
import com.couchbase.transactions.Transactions;



public class SimpleTransaction {


	public Transactions createTansaction(Cluster cluster, TransactionConfig config) {
		return Transactions.create(cluster, config);
	}
	Queue<String> queue=new LinkedList<>();

	public TransactionConfig createTransactionConfig(int expiryTimeout, int changedurability) {
		TransactionConfigBuilder config = TransactionConfigBuilder.create().logDirectlyCleanup(Event.Severity.VERBOSE);
		if (changedurability > 0) {
			switch (changedurability) {
				case 1:
					config.durabilityLevel(TransactionDurabilityLevel.MAJORITY);
					break;
				case 2:
					config.durabilityLevel(TransactionDurabilityLevel.MAJORITY_AND_PERSIST_ON_MASTER);
					break;
				case 3:
					config.durabilityLevel(TransactionDurabilityLevel.PERSIST_TO_MAJORITY);
					break;
				case 4:
					config.durabilityLevel(TransactionDurabilityLevel.NONE);
					break;
				default:
					config.durabilityLevel(TransactionDurabilityLevel.NONE);
			}
		}

		return config.expirationTime(Duration.of(expiryTimeout, ChronoUnit.SECONDS)).build();
	}
	public List<Tuple2<String, JsonObject>> ReadTransaction(Transactions transaction, List<Collection> collections, List<String> Readkeys) {
		List<Tuple2<String, JsonObject>> res = null;
		try {

			TransactionResult result = transaction.run(ctx -> {
				for (String key: Readkeys) {
					for (Collection bucket:collections) {
						if (ctx.get(bucket, key).isPresent()) {
							TransactionJsonDocument doc1=ctx.get(bucket, key).get();
							JsonObject content = doc1.contentAs(JsonObject.class);
							Tuple2<String, JsonObject>mp = Tuples.of(key, content);
							res.add(mp);
						}
					}
				}

			});

		}
		catch (TransactionFailed err) {
			// This per-txn log allows the app to only log failures
			System.out.println("Transaction failed from runTransaction");
			err.result().log().logs().forEach(System.err::println);
		}
		return res;
	}

	public ArrayList<LogDefer> RunTransaction(Transactions transaction, List<Collection> collections, List<Tuple2<String, JsonObject>> Createkeys, List<String> Updatekeys,
											  List<String> Deletekeys, Boolean commit, boolean sync, int updatecount) {
		ArrayList<LogDefer> res = null;
//		synchronous API - transactions
		if (sync) {
			try {

				TransactionResult result = transaction.run(ctx -> {
					//				creation of docs

					for (Collection bucket:collections) {
						for (Tuple2<String, JsonObject> document : Createkeys) {
							TransactionJsonDocument doc=ctx.insert(bucket, document.getT1(), document.getT2());
							TransactionJsonDocument doc1=ctx.get(bucket, document.getT1()).get();
//							JsonObject content = doc1.contentAs(JsonObject.class);
//							if (areEqual(content,document.getT2()));
//							if (content.equals(document.getT2()));
//							else {System.out.println("Document not matched");}
						}

					}
					//				update of docs
					for (String key: Updatekeys) {
						for (Collection bucket:collections) {
							if (ctx.get(bucket, key).isPresent()) {
								TransactionJsonDocument doc2=ctx.get(bucket, key).get();
								for (int i=1; i<=updatecount; i++) {
									JsonObject content = doc2.contentAs(JsonObject.class);
									content.put("mutated", i );
									ctx.replace(doc2, content);
//										TransactionJsonDocument doc1=ctx.get(bucket, key).get();
//										JsonObject read_content = doc1.contentAs(JsonObject.class);

								}
							}

						}
					}
					//			   delete the docs
					for (String key: Deletekeys) {
						for (Collection bucket:collections) {
							if (ctx.get(bucket, key).isPresent()) {
								TransactionJsonDocument doc1=ctx.get(bucket, key).get();
								ctx.remove(doc1);
							}
						}
					}
					//				commit ot rollback the docs
					if (commit) {  ctx.commit(); }
					else { ctx.rollback(); 	 }

//					transaction.close();


				});
//				result.log().logs().forEach(System.err::println);

			}
			catch (TransactionFailed err) {
				// This per-txn log allows the app to only log failures
				System.out.println("Transaction failed from runTransaction");
				err.result().log().logs().forEach(System.err::println);
				res = err.result().log().logs();
			}

		}
		else {
			for (Collection collection:collections) {
				if (Createkeys.size() > 0) {
					res = multiInsertSingelTransaction(transaction, collection, Createkeys, commit); }
				if (Updatekeys.size() > 0) {
					multiUpdateSingelTransaction(transaction, collection, Updatekeys, commit);}
				if (Deletekeys.size() > 0) {
					multiDeleteSingelTransaction(transaction, collection, Deletekeys, commit);}
			}

		}
		return res;
	}

	public ArrayList<LogDefer>  multiInsertSingelTransaction(Transactions transaction, Collection collection, List<Tuple2<String, JsonObject>> createkeys, Boolean commit)
	{
		ArrayList<LogDefer> res = null;
		Tuple2<String, JsonObject> firstDoc = createkeys.get(0);
		List<Tuple2<String, JsonObject>> remainingDocs = createkeys.stream().skip(1).collect(Collectors.toList());
		ReactiveCollection rc = collection.reactive();

		TransactionResult result = transaction.reactive((ctx) -> {

			if (commit)
			{
				// The first mutation must be done in serial
				return ctx.insert(rc, firstDoc.getT1(), firstDoc.getT2())
						.flatMapMany(v -> Flux.fromIterable(remainingDocs)
										.flatMap(doc -> ctx.insert(rc, doc.getT1(), doc.getT2()),
												// Do all these inserts in parallel
												remainingDocs.size()
										)

								// There's an implicit commit so no need to call ctx.commit().  The .then()
								// converts to the
								// expected type
						).then();}
			else
			{
				// The first mutation must be done in serial
				return ctx.insert(rc, firstDoc.getT1(), firstDoc.getT2())
						.flatMapMany(v -> Flux.fromIterable(remainingDocs)
										.flatMap(doc -> ctx.insert(rc, doc.getT1(), doc.getT2()),
												// Do all these inserts in parallel
												remainingDocs.size()
										)

								// There's an implicit commit so no need to call ctx.commit().  The .then()
								// converts to the
								// expected type
						).then(ctx.rollback());}

		}).doOnError(err -> {

			for (LogDefer e : ((TransactionFailed) err).result().log().logs()) {
				// Optionally, log the result to your own logger
				res.add(e);
			}
		}).block();
		return res;
	}


	public void multiUpdateSingelTransaction(Transactions transaction, Collection collection, List<String> ids, Boolean commit) {
		try {
			TransactionResult result = transaction.reactive((ctx) -> {
				return updateMulti(ctx, transaction, collection, ids, commit);
			}).block();
			//System.out.println("result: "+result.log().logs());
		} catch (TransactionFailed e) {
			System.out.println("Transaction " + e.result().transactionId() + " failed:");
			System.out.println("Error: " + e.result());
			for (LogDefer err : e.result().log().logs()) {
				if (err != null)
					System.out.println(err.toString());
			}
		}
	}

	public Mono<Void> updateMulti(AttemptContextReactive acr, Transactions transaction, Collection collection, List<String> ids, Boolean commit){
		ReactiveCollection reactiveCollection=collection.reactive();
		List<String> docToUpdate=ids.parallelStream().collect(Collectors.toList());
		String id1 = docToUpdate.get(0);
		List<String> remainingDocs = docToUpdate.stream().skip(1).collect(Collectors.toList());
		//System.out.println("docs to be updated"+docToUpdate);
		if (commit) {
			return acr.getOrError(reactiveCollection, id1).flatMap(doc-> acr.replace(doc, doc.contentAs(JsonObject.class).put("mutated", 1))).flatMapMany(
					v-> Flux.fromIterable(remainingDocs).flatMap(d -> acr.getOrError(reactiveCollection,d).flatMap(d1-> acr.replace(d1, d1.contentAs(JsonObject.class).put("mutated", 1))),
							remainingDocs.size())).then();}
		else {
			return acr.getOrError(reactiveCollection, id1).flatMap(doc-> acr.replace(doc, doc.contentAs(JsonObject.class).put("mutated", 1))).flatMapMany(
					v-> Flux.fromIterable(remainingDocs).flatMap(d -> acr.getOrError(reactiveCollection,d).flatMap(d1-> acr.replace(d1, d1.contentAs(JsonObject.class).put("mutated", 1))),
							remainingDocs.size())).then(acr.rollback());
		}
	}


	public void multiDeleteSingelTransaction(Transactions transaction, Collection collection, List<String> ids, Boolean commit) {
		try {
			TransactionResult result = transaction.reactive((ctx) -> {
				return deleteMulti(ctx, transaction, collection, ids, commit);
			}).block();
//	            System.out.println("result: ");
//	            for (LogDefer err : result.log().logs()) {
//	                if (err != null)
//	                    System.out.println(err.toString());
//	            }
		} catch (TransactionFailed e) {
			System.out.println("Transaction " + e.result().transactionId() + " failed:");
			System.out.println("Error: " + e.result());
			for (LogDefer err : e.result().log().logs()) {
				if (err != null)
					System.out.println(err.toString());
			}
		}
	}

	public Mono<Void> deleteMulti(AttemptContextReactive acr, Transactions transaction, Collection collection, List<String> ids, Boolean commit){
		ReactiveCollection reactiveCollection=collection.reactive();
		List<String> docToDelete=ids.parallelStream().collect(Collectors.toList());
		String id1 = docToDelete.get(0);
		List<String> remainingDocs = docToDelete.stream().skip(1).collect(Collectors.toList());
		//System.out.println("docs to be deleted"+docToDelete);
		if (commit) {
			return acr.getOrError(reactiveCollection, id1).flatMap(doc-> acr.remove(doc)).thenMany(
					Flux.fromIterable(remainingDocs).flatMap(d -> acr.getOrError(reactiveCollection,d).flatMap(d1-> acr.remove(d1)),
							remainingDocs.size())).then();}
		else {
			return acr.getOrError(reactiveCollection, id1).flatMap(doc-> acr.remove(doc)).thenMany(
					Flux.fromIterable(remainingDocs).flatMap(d -> acr.getOrError(reactiveCollection,d).flatMap(d1-> acr.remove(d1)),
							remainingDocs.size())).then(acr.rollback());
		}
	}


	public List<String> getQueue(int n){
		return this.queue.stream().skip(queue.size() - n).collect(Collectors.toList());
	}


}

