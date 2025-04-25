from arango import ArangoClient

def main():
    client = ArangoClient()

    db = client.db('_system', username='root', password='')

    db_name = 'test_db'
    if not db.has_database(db_name):
        db.create_database(db_name)

    test_db = client.db(db_name, username='root', password='')

    collection_name = 'test_collection'
    if not test_db.has_collection(collection_name):
        test_db.create_collection(collection_name)

    collection = test_db.collection(collection_name)

    doc = {'_key': 'hello', 'message': 'Hello, world!'}
    if not collection.has('hello'):
        collection.insert(doc)
    else:
        collection.update(doc)  # Обновляет документ, если он уже существует

    result = collection.get('hello')
    print(f"Stored message: {result['message']}")

if __name__ == "__main__":
    main()
