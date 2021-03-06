import socketserver
import sys
from pymongo import MongoClient
import json
from bson import json_util

# Setup MongoDB connection
try:
    mongo_client = MongoClient("mongo") # create instance
except:
    print("Could not connect to MongoDB")
db = mongo_client["cse312"]         # create database
chat_collection = db["chat"]        # create chat collection
userID_collection = db["userID"]            # create id collection

# Read filename by and output bytes
def readByteData(filename):
    with open(filename, 'rb') as f:
        return f.read()


# id increased by 1, or create an id starting with 0, updated id will be stored in database
def getNextID():
    filter = {"id": getID()}
    newValue = {"$inc": {"id": 1}}
    userID_collection.update_one(filter, newValue) # update id by one, or id is 0 if not exists
    return userID_collection.find_one({})["id"]

# Get User ID from id collection
def getID():
    # ⚠️ is .count_documents({}) NOT count_documents
    if userID_collection.count_documents({}) == 0: # if no id was found
        userID_collection.insert_one({"id": 0}) # create id with 0
    assert userID_collection.count_documents({}) == 1, "ID is either empty or more than 1"
    return userID_collection.find_one({})["id"]

# MyTCPHandler is also a base handler inherited from BaseRequestHandler
class MyTCPHandler(socketserver.BaseRequestHandler):
    clients = [] # if you want some data persist through all connections, use it

    def handle(self): 
    # while True: # means connection is established
        received_data = self.request.recv(1024)
        # client_id = self.client_address[0] + ":" + str(self.client_address[1]) # 127.0.0.1:65413
        # print("\nClient: " + client_id + " is requesting data")                # 127.0.0.1:65413 is sending data:
        
        # Get decoded HTTP request data and check if it's empty
        decodedRequestData = received_data.decode()            # get decoded HTTP request string data
        print("\n______________Handling HTTP Request___________________")
        if "HTTP/1.1" not in decodedRequestData:
            print("            *** Empty request line ***")
            print("____________________________________________________")
            return
        else:
            print(decodedRequestData)
            print("_____________________________________________________")
    
        # Get method and path from decoded request data
        method, path = self.getMethodPath(decodedRequestData)

        # Parse HTTP request line and return HTTP response
        encodedResponse = self.parseRequestData(method, path, decodedRequestData)

        # Send out response through HTTP and cleanup
        self.request.sendall(encodedResponse)  # send completed response through HTTP
        sys.stdout.flush() # needed to use combine with docker
        sys.stderr.flush() # whatever you have buffer, print it out to the screen

    # get request method, path from request data
    def getMethodPath(self, requestData):
        requestList = requestData.split("\r\n")          # split HTTP request into array by new line symbol
        requestLine = requestList[0].split(" ")          # HTTP request line such as: [GET, /, HTTP/1.1]
        return requestLine[0], requestLine[1]            # get request method, path
        
    # Parse HTTP request data and return HTTP response
    def parseRequestData(self, method, path, requestData):
        if method == "GET":
            encodedResponse = self.parseGET(path)
        elif method == "POST":
            bodyObj = self.getRequestBody(requestData)   # convert json into python obj
            encodedResponse = self.parsePOST( bodyObj)   # Create encoded response
        elif method == "PUT":
            pathID = int(path.split("/users/")[1])       # get integer id from path: "users/{id}"
            bodyObj = self.getRequestBody(requestData)   # convert json into python obj
            encodedResponse = self.parsePUT(pathID, bodyObj)
        elif method == "DELETE":
            pathID = int(path.split("/users/")[1])       # get the record integer id from path
            encodedResponse = self.parseDELETE(pathID)
        else:
            encodedResponse = self.response404()

        return encodedResponse

    # Parse out the record body in a request
    def getRequestBody(sefl, requestData):
        # Parse out the record body that is in the POST request
        body = requestData.split("\r\n\r\n")[1]
        print("HTTP request body length: " + str(len(body.encode())))  # needed to check if the request body is fully received
        return json.loads(body)                                        # convert json into python obj

    # Parse DELETE request and create proper response
    def parseDELETE(self, pathID):
        # Assume that all {id} are well-formed integers.
        result = chat_collection.delete_one({"id": pathID}) # delete record with id
        if result.deleted_count == 0: # number of deleted items
            return self.response404("The record with ID [" + pathID + "] was not found.")
        else:
            return self.response204()
    
    # Parse PUT request and create proper response
    def parsePUT(self, pathID, bodyObj): 
        result = chat_collection.find_one({"id": pathID}) # find record with {id} in the database
        # Update record's content from with found id, or return 404 page if can't find the record
        if result == None:
            return self.response404("404 Page Not Found: No record or the record has been deleted")
        else: 
            filter = {"id": pathID}
            newRecord = {"email": bodyObj["email"], "username": bodyObj["username"]}
            chat_collection.update_one(filter, {"$set": newRecord})             # update new record under pathID 
            updatedRecord = chat_collection.find_one(newRecord, {"_id": False}) # get updated record from database for response
            return self.response200("application/json", json_util.dumps(updatedRecord).encode())

    # Parse GET request and create proper response
    def parseGET(self, path):
        if path == "/" or path == "/index.html":
            return self.response200("text/html; charset=utf-8", readByteData("index.html"))
        elif path == "/style.css":
            return self.response200("text/css", readByteData("style.css"))
        elif path == "/functions.js":
            return self.response200("text/javascript", readByteData("functions.js"))
        elif "/image/" in path:
            return self.response200("image/jpeg", readByteData("image/" + self.getImageFileName(path)))
        elif path == "/users":     # Retrieve all records
            allRecords = self.getAllRecords()
            return self.response200("application/json", json_util.dumps(allRecords).encode())
        elif "/users/" in path: # to retriece single record from path "/users/{id}": /users/1...
            # Assume that all {id} are well-formed integers.
            record_id = int(path.split("/users/")[1])   # get the record id from path
            record = chat_collection.find_one({"id": record_id}, {"_id": False}) # find single record according to id
            if record == None:
                return self.response404("404 Page Not Found: No record in the database")
            else:
                return self.response200("application/json", json_util.dumps(record).encode())
        else:
            return self.response404() # unknown path, return 404 page

    # Parse POST request and create proper response
    def parsePOST(self, bodyObj):
        bodyObj["id"] = getNextID()                  # assign an ID for the new user
        chat_collection.insert_one(bodyObj)          # create records in database
        createdRecord = chat_collection.find_one(bodyObj, {"_id": False})    # get created record but don't show "_id"
        jsonBody = json_util.dumps(createdRecord)
        return self.response201("application/json", jsonBody.encode()) 

    def getAllRecords(self):
        records = [] # a list of all record dicts
        for record in chat_collection.find({}, {"_id": False}):
            records.append(record)
        print(records) # print all records
        return records

    # Parse image request
    def getImageFileName(self, path):
        imageName = path.split("/image/")[1]
        return imageName

    # Construct 200 status response and send out thorught HTTP
    def response200(self, MIMEType, byteData):
        status = "HTTP/1.1 200 OK"
        contentType = "\r\nContent-Type: " + MIMEType
        contentLength = "\r\nContent-Length: " + str(len(byteData))
        noSniff = "\r\nX-Content-Type-Options: nosniff"
        return (status + contentType+ contentLength + noSniff  + "\r\n\r\n").encode() + byteData
    
    # Construct 201 status response and send out thorught HTTP
    def response201(self, MIMEType, byteData):
        status = "HTTP/1.1 201 Created"
        contentType = "\r\nContent-Type: " + MIMEType
        contentLength = "\r\nContent-Length: " + str(len(byteData))
        noSniff = "\r\nX-Content-Type-Options: nosniff"
        return (status + contentType + contentLength + noSniff + "\r\n\r\n").encode() + byteData

    # Construct 404 status response and send out thorught HTTP
    def response404(self, errMsg="Sorry, page cannot be found!"):
        contentLength = "\r\nContent-Length: " + str(len(errMsg.encode()))
        return ("HTTP/1.1 404 Not Found\r\nContent-Type: text/plain" + contentLength + "\r\n\r\n" + errMsg).encode()
    
    def response204(self):
        return "HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n".encode()



if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 8000
    server = socketserver.ThreadingTCPServer( (HOST, PORT), MyTCPHandler )
    server.serve_forever()

# sudo lsof -i:5000          ---> find process using port 5000
# kill $PID                  ---> kill the process on that port
# kill -9 $PID               ---> to forcefully kill the port