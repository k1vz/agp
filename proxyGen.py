from io import TextIOWrapper
import os, json, re

config_file = open('config.json')
config = json.load(config_file)

if not os.path.exists(config['output_path']): 
	os.makedirs(config['output_path'])

methods_with_impact = [method for method, method_data in config['relations'].items() if method_data['impact'] == "true"]
methods_without_impact = [method for method, method_data in config['relations'].items() if method_data['impact'] == "false"]

interfaceFunctions = {}
inside_multiline_comment: bool = False

def cleanLine(line: str):
	global inside_multiline_comment
	
	if '/*' in line and '*/' not in line:
		inside_multiline_comment = True
		line = re.sub(r'/\*.*', '', line)
	
	if inside_multiline_comment and '*/' in line:
		inside_multiline_comment = False
		line = re.sub(r'.*\*/', '', line)
		return line.strip()
	
	if inside_multiline_comment:
		return
	
	line = re.sub(r'//.*', '', line).strip()
	line = re.sub(r'/\*.*?\*/', '', line)  
	
	return line

def readInterfaceFile():
	interfaceFile = open(config['interface_path'], 'r')
	dataTypes = ['void', 'int', 'Data', 'Data[]', 'bool']
	interfaceName = ''

	while True:
		line_raw = interfaceFile.readline()
		if not line_raw:
			break
		
		line = cleanLine(line_raw)
		if line:
			wordList = line.replace('\t', '').replace('\n', '').split(' ')
			if wordList[0] == 'interface':
				interfaceName = wordList[1]
			elif wordList[0] in dataTypes:
				returnType = wordList[0]
				functionName = wordList[1]

				parameterList = line[line.find('(') + 1:line.rfind(')')].split(',')
				parameterList = [param.strip() for param in parameterList if param.strip()]

				numParam = len([param for param in parameterList if not param.startswith("opt")])

				interfaceFunctions[functionName] = {
					"returnType": returnType,
					"interfaceName": interfaceName,
					"parameterList": parameterList,
					"numParam": numParam
				}

	interfaceFile.close()

def writeHeader(output_file:TextIOWrapper, propagateMethod: list[str]):
	output_file.write('''data Param {
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

	if ('sharding' in propagateMethod):
		output_file.write("data ShardState {\n")
		output_file.write("\tInt state[]\n")
		output_file.write("}\n")

	output_file.write('''
/* Available list operations */
const char ADD[]          = "add"
const char GET_LENGTH[]   = "getLength"
const char GET_CONTENTS[] = "getContents"
const char CLEAR_LIST[]   = "clearList"

/* IPs */
const char LOCALHOST[] = "localhost"

component provides List:heap(Destructor, AdaptEvents) requires data.json.JSONEncoder parser,
	net.TCPSocket, data.StringUtil strUtil, io.Output out, data.IntUtil iu, ''')
			
	if ('sharding' in propagateMethod):
		output_file.write("hash.Multiplicative hash")
	
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write("net.TCPServerSocket")

	output_file.write('''
{
	IPAddr remoteDistsIps[] = null
	IPAddr remoteListsIps[] = null
''')

	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write("\tMutex remoteListsIpsLock = new Mutex()\n")
		output_file.write("\tint pointer = 0\n")

	output_file.write('''
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

	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write('''
	void sendMsgToRemoteDists(char msg[]) {
		setupRemoteDistsIPs()
		for (int i = 0; i < remoteDistsIps.arrayLength; i++) {
			connectAndSend(remoteDistsIps[i], msg, true)
		}
	}
	''')

	output_file.write('''
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
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write('''
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
	''')

	if ('propagate' in propagateMethod):
		output_file.write('''
  	void makeGroupRequest(char content[]) {
		setupRemoteListsIPs()
		IPAddr addr = null
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
		  addr = remoteListsIps[i]
		  asynch::connectAndSend(addr, content, true)
		}
	}
	''')
		
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write('''	  
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
	elif ('sharding' in propagateMethod):
		output_file.write('''
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

def writeFooter(output_file:TextIOWrapper, propagateMethod: list[str]):
	output_file.write('''
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
	
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write("sendMsgToRemoteDists(msg)")

	elif ('sharding' in propagateMethod):
	
		output_file.write('''
			setupRemoteDistsIPs()
			for (int i = 0; i < remoteDistsIps.arrayLength; i++) {
				makeRequestSharding(remoteDistsIps[i], msg, true)
			}''')
		
	output_file.write('''
		}
	}

	// this is extremely hardcoded! ):
	void AdaptEvents:active() {
		if (content != null) {''')
	
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		output_file.write('''
			char state[] = parser.jsonFromArray(content, null)
			char msg[] = new char[]("../distributor/RemoteList.o!", state, "\\r\\r\\r\\r")
			sendMsgToRemoteDists(msg)''')


	if ('sharding' in propagateMethod):

		output_file.write('''
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
	output_file.write('''
		}
	}
}''')

def writeFunction(output_file: TextIOWrapper, propagateMethod: str, returnType: str, interfaceName: str, functionName: str, parameterList: list[str], numParam: int):
	parameters = ', '.join(parameterList)	

	output_file.write(f"\t{returnType} {interfaceName}:{functionName} ({parameters}) {{\n")
	output_file.write("\t\tRequest request = new Request()\n")
	output_file.write(f'\t\trequest.functionName = "{functionName}"\n')
	output_file.write(f"\t\trequest.numParams = {numParam}\n")
	output_file.write("\n")
	output_file.write("\t\tchar requestStr[] = parser.jsonFromData(request, null)\n")

	if functionName == 'add':
		paramName = parameterList[0].split()[-1]

		output_file.write(f'\t\tchar param[] = parser.jsonFromData({paramName}, null)\n')
		output_file.write('\t\tchar content2[] = new char[](requestStr, "!", param, "\\r\\r\\r\\r")\n\n')

		if propagateMethod == 'sharding':
			output_file.write("\t\tsetupRemoteListsIPs()\n")
			output_file.write(f'\t\tInt num = {paramName}\n')
			output_file.write('\t\tIPAddr addr = remoteListsIps[hash.h(num.i, remoteListsIps.arrayLength)]\n')
			output_file.write('\t\tmakeRequestSharding(addr, content2, false)\n\n')

		elif propagateMethod == 'alternate':
			output_file.write('\t\tmakeRequest(content2)\n\n')

		elif propagateMethod == 'propagate':
			output_file.write('\t\tmakeGroupRequest(content2)\n')

		output_file.write('\t}\n\n')

	else:
		output_file.write('\t\tchar content2[] = new char[](requestStr, "!", " ", "\\r\\r\\r\\r")\n')

		if functionName == 'getLength':
			if propagateMethod == 'sharding':
				output_file.write('''
		int totalContents = 0
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			totalContents += iu.intFromString(response.value)
		}
		return totalContents\n\n''')

			elif propagateMethod in ['propagate', 'alternate']:
				output_file.write('''
		Response response = makeRequest(content2)
		return iu.intFromString(response.value)\n\n''')

		elif functionName == 'getContents':
			if propagateMethod == 'sharding':
				output_file.write('''
		setupRemoteListsIPs()
		Int contents[] = null
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
			contents = new Int[](contents, nums)
		}
		return contents\n''')

			elif propagateMethod == 'propagate':
				output_file.write('''
		Response response = makeRequest(content2)
		Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
		return nums\n''')

			elif propagateMethod == 'alternate':
				output_file.write('''
		Response response = makeRequest(content2)
		Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
		return nums\n''')

		output_file.write('''\t}\n\n''')

def generateProxyFiles():
	for method_type in ["sharding", "propagate", "mixed_sharding", "mixed_propagate"]:
		with open(f"{config['output_path']}ListCP{method_type}.dn", "w") as output_file:
			if method_type == "mixed_sharding":
				writeHeader(output_file, ["sharding", "alternate"])
				for method in methods_with_impact:
					writeFunction(output_file, "sharding", interfaceFunctions[method]['returnType'], interfaceFunctions[method]['interfaceName'], method, interfaceFunctions[method]['parameterList'], interfaceFunctions[method]['numParam'])
				for method in methods_without_impact:
					writeFunction(output_file, "alternate", interfaceFunctions[method]['returnType'], interfaceFunctions[method]['interfaceName'], method, interfaceFunctions[method]['parameterList'], interfaceFunctions[method]['numParam'])
				writeFooter(output_file, ["sharding", "alternate"])

			elif method_type == "mixed_propagate":
				writeHeader(output_file, ["propagate", "alternate"])
				for method in methods_with_impact:
					writeFunction(output_file, "propagate", interfaceFunctions[method]['returnType'], interfaceFunctions[method]['interfaceName'], method, interfaceFunctions[method]['parameterList'], interfaceFunctions[method]['numParam'])
				for method in methods_without_impact:
					writeFunction(output_file, "alternate", interfaceFunctions[method]['returnType'], interfaceFunctions[method]['interfaceName'], method, interfaceFunctions[method]['parameterList'], interfaceFunctions[method]['numParam'])
				writeFooter(output_file, ["propagate", "alternate"])

			else:
				writeHeader(output_file, [method_type])
				for method in methods_with_impact + methods_without_impact:
					writeFunction(output_file, method_type, interfaceFunctions[method]['returnType'], interfaceFunctions[method]['interfaceName'], method, interfaceFunctions[method]['parameterList'], interfaceFunctions[method]['numParam'])
				writeFooter(output_file, [method_type])

			output_file.close()

readInterfaceFile()
generateProxyFiles()

config_file.close()
