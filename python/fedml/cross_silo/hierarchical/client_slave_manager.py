from ...utils.logging import logger
import torch.distributed as dist

class ClientSlaveManager:
    def __init__(self, args, trainer_dist_adapter):
        self.trainer_dist_adapter = trainer_dist_adapter
        self.args = args
        self.round_idx = 0
        self.num_rounds = args.comm_round
        self.finished = False

    def train(self):
        [round_idx, model_params, client_index] = self.await_sync_process_group()
        if round_idx:
            self.round_idx = round_idx
        if model_params:
            self.trainer_dist_adapter.update_model(model_params)
        if client_index:
            self.trainer_dist_adapter.update_dataset(int(client_index))

        self.trainer_dist_adapter.train(self.round_idx)

        self.round_idx += 1
        if self.round_idx == self.num_rounds:
            # post_complete_message_to_sweep_process(self.args)
            self.finish()

    def finish(self):
        # pass
        self.trainer_dist_adapter.cleanup_pg()
        logger.info(
            "Training finsihded for slave client rank %s in silo %s" % (self.args.silo_proc_rank, self.args.client_rank)
        )
        self.finished = True

    def await_sync_process_group(self, src=0):
        logger.info("prcoess %d waiting for round number" %
                     dist.get_rank())
        objects = [None, None, None]
        dist.broadcast_object_list(
            objects, src=src, group=self.trainer_dist_adapter.process_group_manager.get_process_group())
        logger.info("prcoess %d received round_number %d" %
                     (dist.get_rank(), objects[0]))
        return objects

    def run(self):
        while not self.finished:
            self.train()
