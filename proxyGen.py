# por que no proxy Propagate o "resp" é declarado se não é utilizado? linha 142 do ListCPPropagate
# a linha 192 do commonMethods vai dar problema? reutiliza o nome, porém o conteúdo é diferente. "Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)"

from io import TextIOWrapper
import os, json

config_file = open('config.json')
config = json.load(config_file)
file = open(config['interface_path'], 'r')

if not os.path.exists("result/"): 
    os.makedirs("result/")

inComment = False
methodNames:list[str] = list(config['relations'].keys())
typesSupported:list[str] = ['void', 'integer', 'decimal', 'Data', 'Data[]', 'OBJECT']

interfaceFunctions = {}
enabled_methods_dict = {}
common_methods = {}

for method, method_data in config['relations'].items():
	for propagation_method, propagation_method_data in method_data['propagate_methods'].items():
		if propagation_method_data.get('mode') == 'enabled':
			if propagation_method not in enabled_methods_dict:
				enabled_methods_dict[propagation_method] = []

			if method not in common_methods:
				common_methods[method] = []

			enabled_methods_dict[propagation_method].append(method)
			common_methods[method].append(propagation_method)

def writeHeader(file2:TextIOWrapper, propagateMethod: list[str]):
	file2.write('''data Param {
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
	net.TCPSocket, data.StringUtil strUtil, io.Output out, data.IntUtil iu, ''')
			
	if ('sharding' in propagateMethod):
		file2.write("hash.Multiplicative hash")
	
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		file2.write("net.TCPServerSocket")

	file2.write('''
{
	IPAddr remoteDistsIps[] = null
	IPAddr remoteListsIps[] = null
''')

	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
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

	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
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
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
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
	''')

	if ('propagate' in propagateMethod):
		file2.write('''
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
		file2.write('''	  
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
	}
''')

def writeFooter(file2:TextIOWrapper, propagateMethod: list[str]):
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
	
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		file2.write("sendMsgToRemoteDists(msg)")

	elif ('sharding' in propagateMethod):
	
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
	
	if ('propagate' in propagateMethod or 'alternate' in propagateMethod):
		file2.write('''
			char state[] = parser.jsonFromArray(content, null)
			char msg[] = new char[]("../distributor/RemoteList.o!", state, "\\r\\r\\r\\r")
			sendMsgToRemoteDists(msg)''')


	if ('sharding' in propagateMethod):

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

def writeFunction(file2:TextIOWrapper, propagateMethod: list[str], returnType:str, interfaceName:str, functionName:str, parameterList:list[str], numParam:int):
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
		
		if 'sharding' in propagateMethod:
			file2.write("\t\tsetupRemoteListsIPs()\n")
			file2.write(f'\t\tInt num = {paramName}\n')
			file2.write('\t\tIPAddr addr = remoteListsIps[hash.h(num.i, remoteListsIps.arrayLength)]\n')
			file2.write('\t\tmakeRequestSharding(addr, content2, false)\n\n')

		if 'alternate' in propagateMethod:
			file2.write('\t\tmakeRequest(content2)\n\n')
		
		if 'propagate' in propagateMethod:
			file2.write('\t\tmakeGroupRequest(content2)\n\n')

		file2.write('\t}\n\n')
	else:
		file2.write('\t\tchar content2[] = new char[](requestStr, "!", " ", "\\r\\r\\r\\r")\n')

	if (functionName == 'getLength'):
		
		if 'sharding' in propagateMethod:
				file2.write('''
		int totalContents = 0
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			totalContents += iu.intFromString(response.value)
		}
		return totalContents\n\t}\n''')
				
		if 'propagate' in propagateMethod or 'alternate' in propagateMethod:
				file2.write('''
		Response response = makeRequest(content2)
		return iu.intFromString(response.value)\n\t}\n\n''')
				
	elif functionName == 'getContents':

		if 'sharding' in propagateMethod and ('propagate' in propagateMethod or 'alternate' in propagateMethod):
			file2.write('''
		setupRemoteListsIPs()
		Int contents[] = null
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
			contents = new Int[](contents, nums)
		}
		Response response = makeRequest(content2)
		Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
		
		return contents, nums\n\t}\n''')

		elif 'sharding' in propagateMethod:

			file2.write('''
		setupRemoteListsIPs()
		Int contents[] = null
		for (int i = 0; i < remoteListsIps.arrayLength; i++) {
			Response response = makeRequestSharding(remoteListsIps[i], content2, true)
			Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
			contents = new Int[](contents, nums)
		}
		return contents\n\t}\n''')
			
		elif 'propagate' in propagateMethod or 'alternate' in propagateMethod:
			file2.write('''
		Response response = makeRequest(content2)
		Int nums[] = parser.jsonToArray(response.value, typeof(Int[]), null)
		return nums\n\t}\n''')

def writeEmptyFunction(file2:TextIOWrapper, returnType:str, interfaceName:str, functionName:str, parameterList:list[str]):
	parameter = ''

	for i in parameterList:
		if len(parameterList) > 1 and parameter == '':
			parameter += i + ', '
		else:
			parameter += i

	file2.write(f"\t{returnType} {interfaceName}:{functionName} ({parameter}) {{\n")
	if returnType == 'bool':
		file2.write('\t\treturn false\n\t}\n\n')
	elif returnType == 'Data' or returnType == 'Data[]':
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

while True:
	line = file.readline()
	
	if not cleanComments(line):

		line = line.replace('\t', '')
		line = line.replace('\n', '')

		wordList = [wordItem for wordItem in line.split(' ')]

		if wordList[0] == 'interface':
			interfaceName = wordList[1]

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

			interfaceFunctions[functionName] = {
				"returnType": returnType,
				"interfaceName": interfaceName,
				"parameterList": parameterList,
				"numParam": numParam
			}

	if not line:
		break

def writeNormalFiles():
	for propagation_method, enabled_methods in enabled_methods_dict.items():
		file2 = open(config['output_path'] + "ListCP" + propagation_method + ".dn", 'w')

		writeHeader(file2, propagation_method.split())
		for interfaceFunction, interfaceFunctionData in interfaceFunctions.items():
			if interfaceFunction in enabled_methods:
				writeFunction(file2, propagation_method, interfaceFunctionData['returnType'], interfaceFunctionData['interfaceName'], interfaceFunction, interfaceFunctionData['parameterList'], interfaceFunctionData['numParam'])
			else:
				writeEmptyFunction(file2, interfaceFunctionData['returnType'], interfaceFunctionData['interfaceName'], interfaceFunction, interfaceFunctionData['parameterList'])

		writeFooter(file2, propagation_method)
		file2.close()

def writeCommonMethodsFile():
    file2 = open(config['output_path'] + "ListCPcommonMethods.dn", 'w')

    _, biggestPropagationMethodList = max(common_methods.items(), key=lambda item: len(item[1])) 
    writeHeader(file2, biggestPropagationMethodList)

    for interfaceFunction, interfaceFunctionData in interfaceFunctions.items():
        if interfaceFunction in common_methods:
            enabled_methods = common_methods[interfaceFunction]
            writeFunction(file2, enabled_methods, interfaceFunctionData['returnType'], interfaceFunctionData['interfaceName'], interfaceFunction, interfaceFunctionData['parameterList'], interfaceFunctionData['numParam'])
        else:
            writeEmptyFunction(file2, interfaceFunctionData['returnType'], interfaceFunctionData['interfaceName'], interfaceFunction, interfaceFunctionData['parameterList'])

    writeFooter(file2, biggestPropagationMethodList)
    file2.close()

writeNormalFiles()
writeCommonMethodsFile()

config_file.close()
file.close()