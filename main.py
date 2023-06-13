from tqdm import tqdm
from copy import deepcopy
from tensorboardX import SummaryWriter
from torch.nn.init import xavier_uniform_
from src.utils import config
from src.utils.common import set_seed
from src.model.common import count_parameters, make_infinite
from src.utils.data.loader import prepare_data_seq
from src.model.common import evaluate

def make_model(vocab, dec_num):
    is_eval = config.test
    if config.model == "EmoDT":
        from src.model.EmoDT.model import EmoDT
        model = EmoDT(
            vocab,
            decoder_number=dec_num,
            is_eval=is_eval,
            model_file_path=config.model_path if is_eval else None,
        )
    model.to(config.device)
    for n, p in model.named_parameters():
        if p.dim() > 1 and (n != "embedding.lut.weight" and config.pretrain_emb):
            xavier_uniform_(p)
    print("# PARAMETERS", count_parameters(model))
    return model


def train(model, train_set, dev_set):
    check_iter = 2000
    try:
        model.train()
        best_ppl = 1000
        patient = 0
        writer = SummaryWriter(log_dir=config.save_path)
        weights_best = deepcopy(model.state_dict())
        # NOTE: get a batch of data
        data_iter = make_infinite(train_set)
        for n_iter in tqdm(range(1000000)):
            loss, ppl, bce, acc = model.train_one_batch(next(data_iter), n_iter)
            writer.add_scalars("loss", {"loss_train": loss}, n_iter)
            writer.add_scalars("ppl", {"ppl_train": ppl}, n_iter)
            writer.add_scalars("bce", {"bce_train": bce}, n_iter)
            writer.add_scalars("accuracy", {"acc_train": acc}, n_iter)
            if config.noam:
                writer.add_scalars(
                    "lr", {"learning_rata": model.optimizer._rate}, n_iter
                )

            if (n_iter + 1) % check_iter == 0:
                model.eval()
                model.epoch = n_iter
                loss_val, ppl_val, bce_val, acc_val, _ = evaluate(
                    model, dev_set, ty="valid", max_dec_step=50
                )
                writer.add_scalars("loss", {"loss_valid": loss_val}, n_iter)
                writer.add_scalars("ppl", {"ppl_valid": ppl_val}, n_iter)
                writer.add_scalars("bce", {"bce_valid": bce_val}, n_iter)
                writer.add_scalars("accuracy", {"acc_train": acc_val}, n_iter)
                model.train()
                if n_iter < 12000:
                    continue
                if ppl_val <= best_ppl:
                    best_ppl = ppl_val
                    patient = 0
                    model.save_model(best_ppl, n_iter)
                    weights_best = deepcopy(model.state_dict())
                else:
                    patient += 1
                if patient > 2:
                    break

    except KeyboardInterrupt:
        print("-" * 89)
        print("Exiting from training early")
        model.save_model(best_ppl, n_iter)
        weights_best = deepcopy(model.state_dict())

    return weights_best


def free_train(model, train_set, dev_set):
    check_iter = 1000
    try:
        model.train()
        best_ppl = 1000
        #patient = 0
        writer = SummaryWriter(log_dir=config.save_path)
        weights_best = deepcopy(model.state_dict())
        # NOTE: get a batch of data
        data_iter = make_infinite(train_set)
        for n_iter in tqdm(range(1000000)):
            loss, ppl, bce, acc = model.train_one_batch(next(data_iter), n_iter)

            writer.add_scalars("loss", {"loss_train": loss}, n_iter)
            writer.add_scalars("ppl", {"ppl_train": ppl}, n_iter)
            writer.add_scalars("bce", {"bce_train": bce}, n_iter)
            writer.add_scalars("accuracy", {"acc_train": acc}, n_iter)
            if config.noam:
                writer.add_scalars(
                    "lr", {"learning_rata": model.optimizer._rate}, n_iter
                )

            if (n_iter + 1) % check_iter == 0:
                model.eval()
                model.epoch = n_iter
                loss_val, ppl_val, bce_val, acc_val, _ = evaluate(
                    model, dev_set, ty="valid", max_dec_step=50
                )
                writer.add_scalars("loss", {"loss_valid": loss_val}, n_iter)
                writer.add_scalars("ppl", {"ppl_valid": ppl_val}, n_iter)
                writer.add_scalars("bce", {"bce_valid": bce_val}, n_iter)
                writer.add_scalars("accuracy", {"acc_train": acc_val}, n_iter)
                model.train()
                if 16000 <= n_iter + 1 <= 32000:
                    best_ppl = ppl_val
                    #patient = 0
                    model.save_model(best_ppl, n_iter)
                    if n_iter + 1 == 22000:
                        weights_best = deepcopy(model.state_dict())
                elif n_iter + 1 > 32000:
                    break

    except KeyboardInterrupt:
        print("-" * 89)
        print("Exiting from training early")
        model.save_model(best_ppl, n_iter)
        weights_best = deepcopy(model.state_dict())

    return weights_best

def test(model, test_set):
    model.eval()
    model.is_eval = True
    loss_test, ppl_test, bce_test, acc_test, results = evaluate(
        model, test_set, ty="test", max_dec_step=50
    )
    file_summary = config.save_path + "/results.txt"
    with open(file_summary, "w") as f:
        f.write("EVAL\tLoss\tPPL\tAccuracy\n")
        f.write(
            "{}\t{:.4f}\t{:.4f}\t{:.4f}\n".format(
                loss_test, ppl_test, bce_test, acc_test
            )
        )
        for r in results:
            f.write(r)


def main():
    # NOTE: 版本更新需要改动main.py 1处, common.py 4处, 如果使用beam_search， 还需在decode/baki.py设计新的Translator
    set_seed()  # for reproducibility

    train_set, dev_set, test_set, vocab, dec_num = prepare_data_seq(
        batch_size=config.batch_size
    )

    model = make_model(vocab, dec_num)

    if config.test:
        test(model, test_set)
    else:
        #weights_best = train(model, train_set, dev_set)
        weights_best = free_train(model, train_set, dev_set)
        model.epoch = 1
        model.load_state_dict({name: weights_best[name] for name in weights_best})
        test(model, test_set)


if __name__ == "__main__":
    main()