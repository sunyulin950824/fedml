import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../../../")))
sys.path.insert(0, os.path.abspath(
    os.path.join(os.getcwd(), "../../../../../FedML")))
import time
import decimal
import csv
import torch.multiprocessing as mp
import torch.distributed.rpc as rpc
import torch
from fedml_api.distributed.utils.ip_config_utils import build_ip_table
from fedml_api.distributed.fedavg.utils import transform_tensor_to_list
from fedml_core.distributed.communication.trpc.trpc_server import TRPCCOMMServicer
from fedml_core.distributed.communication.observer import Observer
from fedml_core.distributed.communication.message import Message
from fedml_core.distributed.communication.base_com_manager import BaseCommunicationManager
import logging
from typing import List
import threading



lock = threading.Lock()


WORKER = "worker{}"


class TRPCCommManager(BaseCommunicationManager):
    def __init__(self,
                 trpc_master_config_path,
                 client_id=0,
                 client_num=0,
                 ):
        logging.info("using TRPC backend")
        with open(trpc_master_config_path, newline='') as csv_file:
            csv_reader = csv.reader(csv_file)
        # skip header line
            next(csv_reader)
            master_address, master_port = next(csv_reader)
        self.master_address = master_address
        self.master_port = master_port
        self.client_id = client_id
        self.client_num = client_num
        self._observers: List[Observer] = []

        if client_id == 0:
            self.node_type = "server"
        else:
            self.node_type = "client"

        print(f"Worker rank {client_id} initializing RPC")

        self.trpc_servicer = TRPCCOMMServicer(
            master_address, master_port, client_num, client_id)
        logging.info(os.getcwd())

        os.environ['MASTER_ADDR'] = self.master_address
        os.environ['MASTER_PORT'] =  self.master_port

        rpc.init_rpc(
            name=WORKER.format(client_id),
            rank=client_id,
            world_size=client_num,  backend=rpc.BackendType.TENSORPIPE,
                 rpc_backend_options=rpc.TensorPipeRpcBackendOptions(
                     rpc_timeout=6000,
                     init_method='env://',
                     _transports=["uv"],
                 ))

        self.is_running = True
        print("server started. master address: " + str(master_address))

    def send_message(self, msg: Message):
        receiver_id = msg.get_receiver_id()

        logging.info("sending message to {}".format(receiver_id))

        # Shoul I wait?
        rpc.rpc_sync(WORKER.format(receiver_id), TRPCCOMMServicer.sendMessage,
                           args=(self.client_id, msg))

        logging.debug("sent")

    def add_observer(self, observer: Observer):
        self._observers.append(observer)

    def remove_observer(self, observer: Observer):
        self._observers.remove(observer)

    def handle_receive_message(self):
        thread = threading.Thread(target=self.message_handling_subroutine)
        thread.start()

    def message_handling_subroutine(self):
        while self.is_running:
            if self.trpc_servicer.message_q.qsize() > 0:
                lock.acquire()
                msg = self.trpc_servicer.message_q.get()
                self.notify(msg)
                lock.release()
        return

    def stop_receive_message(self):
        rpc.shutdown()
        self.is_running = False

    def notify(self, message: Message):
        msg_type = message.get_type()
        for observer in self._observers:
            observer.receive_message(msg_type, message)


def run_worker(rank, world_size):
    r"""
    A wrapper function that initializes RPC, calls the function, and shuts down
    RPC.
    """
    if rank == 1:
        com_manager_client = TRPCCommManager("./trpc_master_config.csv",rank, world_size)
        start = time.time()
        tensor = torch.ones(1000, 1000)
        message = Message(type="test", sender_id=rank, receiver_id="1")
        message.add_params("THE_TENSOR", tensor)
        TRPCCOMMServicer.sendMessage("worker0",message)
        message_values = []
        message = Message(type="test", sender_id=rank, receiver_id="1")
        message2 = Message(type="test", sender_id=rank, receiver_id="1")
        message.add_params("THE_TENSOR", tensor)
        for i in range(100):
            print("###############################")
            print("Measuring for Single Message")
            for size in [100, 1000, 10000]:
                
            #for size in [100, 1000]:
                print(f"======= size = {size} =====")
                tensor = torch.ones(size, size)
                start = time.time()
                TRPCCOMMServicer.sendMessageTest1("worker0",message)
                end = time.time()
                duration = end - start
                message_values.append(duration)
                # print(f"Message tensor size={size} duration={str(duration)}", flush=True)


            print("###############################")
            print("Measuring for Message with separate Tensor")
            sinle_tensor_values = []
            start = time.time()
            for size in [100, 1000, 10000]:
                
            #for size in [100, 1000]:
                print(f"======= size = {size} =====")
                tensor = torch.ones(size, size)
                # message = Message(type="test", sender_id=rank, receiver_id="1")
                # message.add_params("THE_TENSOR", tensor)
                start = time.time()
                TRPCCOMMServicer.sendMessageTest2("worker0",message2.get_params(), tensor)
                end = time.time()
                duration = end - start
                # print(f"Single tensor size={size} duration={str(duration)}", flush=True)
                sinle_tensor_values.append(duration)

        print()
        print()
        print()
        print()
        print("mean message: "+ str(decimal.Decimal(sum(message_values)/len(message_values))))
        print("mean single tensor: "+ str(decimal.Decimal(sum(sinle_tensor_values)/len(sinle_tensor_values))))
        # ret = rpc.rpc_sync("worker1", TRPCCOMMServicer., args=(torch.ones(2), torch.ones(2)))
    else:
        # parameter server does nothing
        com_manager_client = TRPCCommManager("./trpc_master_config.csv",rank, world_size)

    rpc.shutdown()


if __name__ == "__main__":
    world_size = 2
    # run_worker(0,1)
    mp.spawn(run_worker, args=(world_size,), nprocs=world_size, join=True)