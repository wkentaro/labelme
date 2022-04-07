from openvino.inference_engine import IENetwork, IECore


class Network:
    def __init__(self, xml_path, bin_path, batch_size):
        self.xml_path = xml_path
        self.bin_path = bin_path
        self.plugin = None
        self.network = None
        self.input_blob = None
        self.exec_network = None
        self.infer_request = None
        self.batch_size = batch_size
        self.config = {
            "CPU_THROUGHPUT_STREAMS": "4"
            #,"DYN_BATCH_ENABLED": "YES"
        }


    def load_model(self):
        self.plugin = IECore()
        self.network = self.plugin.read_network(model=self.xml_path, weights=self.bin_path)
        self.input_layer_shape = self._get_input_shape()
        input_layer = next(iter(self.network.input_info))
        self.network.reshape({input_layer: (self.batch_size,1,self.input_layer_shape[-2],self.input_layer_shape[-1])})
        
        ### Defining CPU Extension path
        # CPU_EXT_PATH = "/opt/intel/openvino/deployment_tools/inference_engine/lib/intel64/ libcpu_extension_sse4.so"           ### Adding CPU Extension
        # self.plugin.add_extension(CPU_EXT_PATH,"CPU")        ### Get the supported layers of the network
        # supported_layers = self.plugin.query_network(network=self.network, device_name="CPU")          ### Finding unsupported layers
        # unsupported_layers = [l for l in self.network.layers.keys() if l not in supported_layers]            ### Checking for unsupported layers
        # if len(unsupported_layers) != 0:
        #     print("Unsupported layers found")
        #     print(unsupported_layers)
        #     exit(1)        ### Loading the network
        self.exec_network = self.plugin.load_network(self.network,"GPU",num_requests=8)
        # self.exec_network.set_config(self.config)
        self.input_blob  = next(iter(self.network.input_info))
    def _get_input_shape(self):
        return self.network.input_info["inputs"].input_data.shape  
    def synchronous_inference(self,image):  
        return self.exec_network.infer({self.input_blob: image})
    def async_inference(self,image):
        # currently not working
        self.exec_network.requests[0].async_infer({self.input_blob: image})
        request_status = self.exec_network.requests[0].wait(0)
        return self.exec_network.requests[0].output_blobs['output/Sigmoid']
        

    def extract_output(self):
        return self.exec_network.requests[0].output_blobs