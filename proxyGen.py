import json

config_file = open('config.json')
config = json.load(config_file)
file = open(config['interface_path'], 'r')
file2 = open(config['output_path'], 'w')

inComment = False
methodNames:list[str] = list(config['relations'].keys())
typesSupported:list[str] = ['void', 'integer', 'decimal', 'Data', 'Data[]', 'OBJECT']

enabled_methods = {}
for relation, relation_data in config['relations'].items():
    for method, method_data in relation_data['propagate_methods'].items():
        if method_data.get('mode') == 'enabled':
            if method not in enabled_methods:
                enabled_methods[method] = []

            enabled_methods[method].append(relation)

print(enabled_methods)

def writeHeader():
	global file2
	
	file2.write('''
data Param {
	char value[]
}

data Request {
	char functionName[]
	int numParams
	Param params[]
}

data Response {
	// 1 OK - 2 FAILED
	byte status
	// if it's null or "" this has to be translated to null
	char value[]
}

data IPAddr {
	char ip[]
	int port
}

data Int {
	int i
}

''')

	if (len(enabled_methods['sharding']) > 0):
		file2.write("data ShardState {\n")
		file2.write("\tInt state[]\n")
		file2.write("}\n")

	file2.write('''
/* Available list operations */
const char ADD[]          = "add"
const char GET_LENGTH[]   = "getLength"
const char GET_CONTENTS[] = "getContents"
const char CLEAR_LIST[]   = "clearList"

/* IPs */
const char LOCALHOST[] = "localhost"

component provides List:heap(Destructor, AdaptEvents) requires data.json.JSONEncoder parser,
	net.TCPSocket, data.StringUtil strUtil, io.Output out, data.IntUtil iu,''')
			
	if (len(enabled_methods['sharding']) > 0):
		file2.write("hash.Multiplicative hash")

	file2.write('''
{
	IPAddr remoteDistsIps[] = null
	IPAddr remoteListsIps[] = null
''')

	if (len(enabled_methods['propagate']) > 0) or (len(enabled_methods['alternate']) > 0):
		file2.write("\tMutex remoteListsIpsLock = new Mutex()\n")
		file2.write("\tint pointer = 0\n")

	file2.write('''
	void setupRemoteDistsIPs() {
		if (remoteDistsIps == null) {
			remoteDistsIps = new IPAddr[2]
			remoteDistsIps[0] = new IPAddr()
			remoteDistsIps[0].ip = new char[](LOCALHOST)
			remoteDistsIps[0].port = 8081
			remoteDistsIps[1] = new IPAddr()
			remoteDistsIps[1].ip = new char[](LOCALHOST)
			remoteDistsIps[1].port = 8082
		}
	}

	void setupRemoteListsIPs() {
		if (remoteListsIps == null) {
			remoteListsIps = new IPAddr[2]
			remoteListsIps[0] = new IPAddr()
			remoteListsIps[0].ip = new char[](LOCALHOST)
			remoteListsIps[0].port = 2010
			remoteListsIps[1] = new IPAddr()
			remoteListsIps[1].ip = new char[](LOCALHOST)
			remoteListsIps[1].port = 2011
		}
	}
''')

	if (len(enabled_methods['propagate']) > 0) or (len(enabled_methods['alternate']) > 0):
		file2.write('''
	void sendMsgToRemoteDists(char msg[]) {
		setupRemoteDistsIPs()
		for (int i = 0; i < remoteDistsIps.arrayLength; i++) {
			connectAndSend(remoteDistsIps[i], msg, true)
		}
	}
	''')

	file2.write('''
	Response parseResponse(char content[]) {
		String helper[] = strUtil.explode(content, "!")
		Response response
		if (helper.arrayLength > 1) {
			response = parser.jsonToData(helper[0].string, typeof(Response), null)
			Response response2 = new Response()
			response2.value = helper[1].string
			response2.status = response.status
			response = response2
		} else {
			response = parser.jsonToData(content, typeof(Response), null)
		}
		return response
	}

	Response readResponse(TCPSocket s) {
		Response response = null
		char buf[] = null
		int len = 0
		char command[] = null
		while ((buf = s.recv(1)).arrayLength > 0) {
			command = new char[](command, buf)
			len++
			//stop condition
			if (len >= 4) {
				if ((command[len-4] == "\\r") && (command[len-3] == "\\r") &&
					(command[len-2] == "\\r") && (command[len-1] == "\\r")) {
					response = parseResponse(strUtil.subString(command,
						0, command.arrayLength-4))
					break
				}
			}
		}
		if (response == null) { s.disconnect() }
		return response
	}

	bool establishConnection(IPAddr addr, TCPSocket remoteObj) {
		if (!remoteObj.connect(addr.ip, addr.port)) {
			out.println("Connection error!")
			return false
		}
		return true
	}
''')

	if (len(enabled_methods['propagate']) > 0) or (len(enabled_methods['alternate']) > 0):
		file2.write('''
	Response connectAndSend(IPAddr addr, char content[], bool readResponse) {
		TCPSocket remoteObj = new TCPSocket()
		Response resp = null
		if (establishConnection(addr, remoteObj)) {
			remoteObj.send(content)
			if (readResponse) { resp = readResponse(remoteObj) }
			remoteObj.disconnect()
		}
		return resp
	}
			
	Response makeRequest(char content[]) {
		setupRemoteListsIPs()
		IPAddr addr = null
		mutex(remoteListsIpsLock) {
			if (remoteListsIps.arrayLength > 1) {
				if (pointer == remoteListsIps.arrayLength) { pointer = 0 }
				addr = remoteListsIps[pointer]
				pointer++
			} else { out.println("ERROR!") }
		}
		return connectAndSend(addr, content, true)
	}

''')
	elif (len(enabled_methods['sharding']) > 0):
		file2.write('''
	Response makeRequestSharding(IPAddr addr, char content[], bool readResponse) {
	TCPSocket remoteObj = new TCPSocket()
		Response resp = null
		if (establishConnection(addr, remoteObj)) {
			remoteObj.send(content)
			if (readResponse) { resp = readResponse(remoteObj) }
			remoteObj.disconnect()
		}
		return resp
	}\n\n''')

def writeFooter():
	global file2

	file2.write('''
	void buildFromArray(Data items[]) {
		// TODO
	}

	bool List:clone(Object o) {
		// TODO
		return false
	}

	void clearList() {
		// TODO
	}

	void Destructor:destroy() {
	}

	void AdaptEvents:inactive() {
		if (content != null) {
			content = getContents()
			char msg[] = new char[]("clearList!\\r\\r\\r\\r")
			''')
	
	if (len(enabled_methods['propagate']) > 0) or (len(enabled_methods['alternate']) > 0):
		file2.write("sendMsgToRemoteDists(msg)")

	elif len(enabled_methods['sharding']):
	
		file2.write('''
			setupRemoteDistsIPs()
			for (int i = 0; i < remoteDistsIps.arrayLength; i++) {
				makeRequestSharding(remoteDistsIps[i], msg, true)
			}''')
		
	file2.write('''
		}
	}

	// this is extremely hardcoded! ):
	void AdaptEvents:active() {
		if (content != null) {''')
	
	if (len(enabled_methods['propagate']) > 0) or (len(enabled_methods['alternate']) > 0):
		file2.write('''
			char state[] = parser.jsonFromArray(content, null)
			char msg[] = new char[]("../distributor/RemoteList.o!", state, "\\r\\r\\r\\r")
			sendMsgToRemoteDists(msg)''')


	if (len(enabled_methods['sharding']) > 0):

		file2.write('''
			setupRemoteDistsIPs()
			ShardState shardState[] = new ShardState[remoteDistsIps.arrayLength]
			Thread thread[] = new Thread[remoteDistsIps.arrayLength]
			for (int i = 0; i < content.arrayLength; i++) {
				Int num = content[i]
				int remoteIdx = hash.h(num.i, remoteDistsIps.arrayLength)
				if (shardState[remoteIdx] == null) {
					shardState[remoteIdx] = new ShardState()
				}
				shardState[remoteIdx].state = new Int[](shardState[remoteIdx].state, num)
			}
			for (int i = 0; i < remoteDistsIps.arrayLength; i++) {
				char state[] = parser.jsonFromArray(shardState[i].state, null)
				char msg[] = new char[]("../distributor/RemoteList.o!", state, "\\r\\r\\r\\r")
				thread[i] = asynch::makeRequestSharding(remoteDistsIps[i], msg, true)
			}
			for (int i = 0; i < remoteDistsIps.arrayLength; i++) {
				thread[i].join()
			}
			''')
	file2.write('''
		}
	}
}''')

def writeFunction(propagateMethod:str, returnType:str, interfaceName:str, functionName:str, parameterList:list[str], numParam:int):
	global file2
	parameter = ''

	for i in parameterList:
		if len(parameterList) > 1 and parameter == '':
			parameter += i + ', '
		else:
			parameter += i

	file2.write(f"\t{returnType} {interfaceName}:{functionName} ({parameter}) {{\n")
	file2.write("\t\tRequest request = new Request()\n")
	file2.write(f'\t\trequest.functionName = "{functionName}"\n')
	file2.write(f"\t\trequest.numParams = {numParam}\n")
	file2.write("\n")
	file2.write("\t\tchar requestStr[] = parser.jsonFromData(request, null)\n")

	if functionName == 'add':
		paramName = parameterList[0].split()[-1]

		file2.write(f'\t\tchar param[] = parser.jsonFromData({paramName}, null)\n')
		file2.write('\t\tchar content2[] = new char[](requestStr, "!", param, "\\r\\r\\r\\r")\n')
		file2.write("\n")		
		
		if propagateMethod == "sharding":
			file2.write(f'\t\tInt num = {paramName}\n')
			file2.write('\t\tIPAddr addr = remoteListsIps[hash.h(num.i, remoteListsIps.arrayLength)]\n')
			file2.write('\t\tmakeRequestSharding(addr, content2, false)\n\n')

		elif propagateMethod == "propagate" or propagateMethod == "alternate":
			file2.write('\t\tmakeRequest(content2)\n\n')

		file2.write('\t}\n\n')
	else:
		file2.write('\t\tchar content2[] = new char[](requestStr, "!", " ", "\\r\\r\\r\\r")\n')

	if (functionName == 'getLength'):
		
		if propagateMethod == "sharding":
				file2.write('''
		int totalContents = 0
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			totalContents += iu.intFromString(response.value)
		}
		return totalContents\n\t}\n''')
				
		elif propagateMethod == "propagate" or propagateMethod == "alternate":
				file2.write('''
		Response response = makeRequest(content2)
		return iu.intFromString(response.value)\n\t}\n\n''')
				
	elif functionName == 'getContents':

		if propagateMethod == "sharding":

			file2.write('''
		setupRemoteListsIPs()
		Int contents[] = null
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
			contents = new Int[](contents, nums)
		}
		return contents\n\t}\n''')
			
		elif propagateMethod == "propagate" or propagateMethod == "alternate":
			file2.write('''
		Response response = makeRequest(content2)
		Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
		return nums\n\t}\n''')

def writeEmptyFunction(returnType:str, interfaceName:str, functionName:str, parameterList:list[str]):
	global file2
	parameter = ''

	for i in parameterList:
		if len(parameterList) > 1 and parameter == '':
			parameter += i + ', '
		else:
			parameter += i

	file2.write(f"\t{returnType} {interfaceName}:{functionName} ({parameter}) {{\n")
	if returnType == 'bool':
		file2.write('\t\treturn false\n\t}\n\n')
	elif returnType == 'Data':
		file2.write('\t\treturn null\n\t}\n\n')
	else:
		file2.write('\t}\n\n')

def cleanComments(line):
	global inComment
	stripped_line = line.strip()

	if not stripped_line:
		return True
	
	if stripped_line.startswith('//'):
		return True
	
	if stripped_line.startswith('/*') and stripped_line.endswith('*/'):
		return True
	
	if '/*' in stripped_line:
		inComment = True

	if '*/' in stripped_line:
		inComment = False
		return True

	if inComment:
		return True
	
	return not stripped_line.strip()

writeHeader()

while True:
	line = file.readline()
	
	if not cleanComments(line):

		firstRun = True
		line = line.replace('\t', '')
		line = line.replace('\n', '')

		wordList = []
		for wordItem in line.split(' '):
			wordList.append(wordItem)

		#interfaceName
		if wordList[0] == 'interface':
			interfaceName = wordList[1]

		#functions
		if wordList[0] in typesSupported:
			returnType = wordList[0]
			functionName = wordList[1]
			isParameter = False

			parameterList = line[line.find('(') + len('('):line.rfind(')')].split(',') # get the contents of the line between parentheses and split by comma
			parameterList = [parameter.strip() for parameter in list(filter(None, parameterList))] # clean white spaces in itens and clean empty items

			if (parameterList and not parameterList[0].startswith('opt')):
				numParam = len(parameterList)
			else:
				numParam = 0

			for method, methodData in enabled_methods.items():
				if functionName in methodData:
					writeFunction(method, returnType, interfaceName, functionName, parameterList, numParam)
				elif (not functionName in methodData) and firstRun:
					writeEmptyFunction(returnType, interfaceName, functionName, parameterList)
					firstRun = False # avoid the method run more than once without changes

	if not line:
		break

writeFooter()

config_file.close()
file2.close()
file.close()