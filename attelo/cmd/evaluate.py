"run cross-fold evaluation"

from __future__ import print_function
import itertools
import sys

from ..args import\
    (add_common_args, add_learner_args,
     add_report_args,
     args_to_decoder,
     args_to_decoding_mode,
     args_to_learners,
     args_to_rng)
from ..decoding import\
    (decode, Models)
from ..fold import make_n_fold
from ..io import (load_data_pack)
from ..table import (for_attachment, for_labelling)
from ..report import Report
from .decode import score_prediction


def best_prediction(dpack, predictions):
    """
    Return the best prediction for the given data along with its
    score. Best is defined in a recall-centric way, by the number
    of correct labels made (or if in attach-only mode, the number
    of correct decisions to attach).

    :param relate: if True, labels (relations) are to be evaluated too
                   otherwise only attachments
    :param predicted: a single prediction (list of id, id, label tuples)
    """
    def score(prediction):
        'score a single prediction'
        return score_prediction(dpack, prediction)

    max_key = lambda x: score(x).correct_label
    return max(predictions, key=max_key)


def config_argparser(psr):
    "add subcommand arguments to subparser"

    add_common_args(psr)
    add_learner_args(psr)
    add_report_args(psr)
    psr.set_defaults(func=main)
    psr.add_argument("--nfold", "-n",
                     default=10, type=int,
                     help="nfold cross-validation number (default 10)")
    psr.add_argument("-s", "--shuffle",
                     default=False, action="store_true",
                     help="if set, ensure a different cross-validation "
                     "of files is done, otherwise, the same file "
                     "splitting is done everytime")
    psr.add_argument("--unlabelled", "-u",
                     default=False, action="store_true",
                     help="force unlabelled evaluation, even if the "
                     "prediction is made with relations")


def _learn_for_fold(dpack, fold_dict, fold,
                    attach_learner, relate_learner):
    '''
    learn models for the training data in the given fold

    :rtype :py:class:Models:
    '''
    training_pack = dpack.training(fold_dict, fold)
    attach_pack = for_attachment(training_pack)
    relate_pack = for_labelling(training_pack)
    attach_model = attach_learner.fit(attach_pack.data,
                                      attach_pack.target)
    relate_model = relate_learner.fit(relate_pack.data,
                                      relate_pack.target)
    return Models(attach=attach_model, relate=relate_model)


def _decode_group(mode, decoder, dpack, models):
    '''
    decode and score a single group

    :rtype Count
    '''
    predictions = decode(mode, decoder, dpack, models)
    best = best_prediction(dpack, predictions)
    return score_prediction(dpack, best)


def _decode_fold(mode, decoder, dpack, models):
    '''
    decode and score all groups in the pack
    (pack should be whittled down to test set for
    a given fold)

    :rtype [Count]
    '''
    scores = []
    for onedoc, indices in dpack.groupings().items():
        print("decoding on file : ", onedoc, file=sys.stderr)
        onepack = dpack.selected(indices)
        score = _decode_group(mode, decoder, onepack, models)
        scores.append(score)
    return scores


def main(args):
    'subcommand main'

    dpack = load_data_pack(args.edus, args.features)
    # print(args, file=sys.stderr)
    decoder = args_to_decoder(args)
    decoding_mode = args_to_decoding_mode(args)

    # TODO: more models for intra-sentence
    attach_learner, relate_learner = args_to_learners(decoder, args)

    fold_dict = make_n_fold(dpack, args.nfold,
                            args_to_rng(args))

    evals = []
    # --- fold level -- to be refactored
    for fold in range(args.nfold):
        print(">>> doing fold ", fold + 1, file=sys.stderr)
        print(">>> training ... ", file=sys.stderr)

        models = _learn_for_fold(dpack, fold_dict, fold,
                                 attach_learner,
                                 relate_learner)
        fold_evals = _decode_fold(decoding_mode,
                                  decoder,
                                  dpack.testing(fold_dict, fold),
                                  models)
        fold_report = Report(fold_evals,
                             params=args,
                             correction=args.correction)
        print("Fold eval:", fold_report.summary())
        evals.append(fold_evals)
        # --end of file level
    # --- end of fold level
    # end of test for a set of parameter
    report = Report(list(itertools.chain.from_iterable(evals)),
                    params=args,
                    correction=args.correction)
    print(">>> FINAL EVAL:", report.summary())
