#!/usr/bin/python3

import yaml
import json
import os
from pathlib import Path
import argparse
import itertools

import jsonpath_ng


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-t', dest='test', action='store_true',
        default=False, help='use data_test directory instead of data directory'
    )
    parser.add_argument(
        '-j', dest='json', action='store_true',
        default=False, help='output json file instead of jsonl file'
    )
    parser.add_argument('yaml_filename', type=str)

    return parser.parse_args()


# https://stackoverflow.com/questions/5228158/cartesian-product-of-a-dictionary-of-lists
def product_dict(list_dict: dict):
    keys = list_dict.keys()
    vals = list_dict.values()
    for instance in itertools.product(*vals):
        yield dict(zip(keys, instance))


def get_length_from_dict(
    log: dict, depth: int, path: str, log_indices_all: dict
) -> None:
    """
    dict型のlogから、配列をすべて展開したものをlog_indices_allに格納する
    --- example ---
    input(log):
    {
        'ROOT': {
            'a': {
                'id': [1, 2]
            }
        }
    }
    result(log_indices_all):
    {
        (0, '$'): [{'ROOT': -2}],
        (1, '$.ROOT'): [{'a': -2}],
        (2, '$.ROOT.a'): [{'id': 0}, {'id': 1}],
        (3, '$.ROOT.a.id[0]'): [1],
        (3, '$.ROOT.a.id[1]'): [2]
    }
    (-2: dict, -1: value, others: index)
    """
    log_length = {}
    for k, v in log.items():
        path_next = f'{path}.{k}' if path != '' else k
        if isinstance(v, list):
            log_length[k] = len(v)
            get_length_from_list(v, depth + 1, path_next, log_indices_all)
        elif isinstance(v, dict):
            log_length[k] = -2
            get_length_from_dict(v, depth + 1, path_next, log_indices_all)
        else:
            log_length[k] = -1

    log_indices = {k: list(range(v)) if v not in [-1, -2] else [v] for k, v in log_length.items()}
    if len(log_indices) > 0 or depth == 0:
        log_indices_all[depth, path] = list(product_dict(log_indices))


def get_length_from_list(
    log: list, depth: int, path: str, log_indices_all: dict
) -> None:
    """
    list型のlogから、配列をすべて展開したものをlog_indices_allに格納する
    """
    for i, v in enumerate(log):
        path_next = f'{path}[{i}]'
        if isinstance(v, list):
            get_length_from_list(v, depth, path_next, log_indices_all)
        elif isinstance(v, dict):
            get_length_from_dict(v, depth, path_next, log_indices_all)
        else:
            log_indices_all[depth, path_next] = [v]


def get_path(log_indices_all: dict):
    """
    path(JSONPath)の組み合わせのうち、有効なものを抽出する(重複排除)
    (generator)
    --- example ---
    input:
    {
        (0, '$'): [{'ROOT': -2}],
        (1, '$.ROOT'): [{'a': -2}],
        (2, '$.ROOT.a'): [{'id': 0}, {'id': 1}],
        (3, '$.ROOT.a.id[0]'): [1],
        (3, '$.ROOT.a.id[1]'): [2]
    }
    output:
    [
        {
            (0, '$'): {'ROOT': -2},
            (1, '$.ROOT'): {'a': -2},
            (2, '$.ROOT.a'): {'id': 0},
            (3, '$.ROOT.a.id[0]'): 1
        },
        {
            (0, '$'): {'ROOT': -2},
            (1, '$.ROOT'): {'a': -2},
            (2, '$.ROOT.a'): {'id': 1},
            (3, '$.ROOT.a.id[1]'): 2
        }
    ]
    """
    log_indices_all_keys = []
    for log_indices in product_dict(log_indices_all):
        indices = {}
        keys = sorted(list(log_indices.keys()), key=lambda key: key[0])
        for depth, key_path in keys:
            if depth == 0:
                # rootは無条件で入れる
                indices[depth, key_path] = log_indices[depth, key_path]
            else:
                # 既存のpathから生成されるpathすべて
                # list, value
                key_path_all = [f'{key_path}.{k}[{i}]' for (_, key_path), index in indices.items() if isinstance(index, dict) for k, i in index.items() if i != -2]
                # dict
                key_path_all += [f'{key_path}.{k}' for (_, key_path), index in indices.items() if isinstance(index, dict) for k, i in index.items() if i == -2]
                if key_path in key_path_all:
                    indices[depth, key_path] = log_indices[depth, key_path]
        
        # 重複チェック
        log_indices_keys = '|'.join(str(k) for k in indices.keys())
        if log_indices_keys not in log_indices_all_keys:
            log_indices_all_keys.append(log_indices_keys)
            yield indices

# https://utamaro.hatenablog.jp/entry/2018/10/17/064721
def get_json(
    depth: int, path: str, log_indices: dict, log_original: dict
):
    """
    path(JSONPath)の組み合わせから、dict(json)を生成する
    --- example ---
    input(log_indices):
    {
        (0, '$'): {'ROOT': -2},
        (1, '$.ROOT'): {'a': -2},
        (2, '$.ROOT.a'): {'id': 0},
        (3, '$.ROOT.a.id[0]'): 1
    }
    output:
    { 'ROOT': { 'a': { 'id': 1 } } }
    """
    keys_next = log_indices[depth, path]
    jsonpath_expr = jsonpath_ng.parse(path)
    matches = jsonpath_expr.find(log_original)
    # 必ず1つだけ見つかる
    log_indices_base = [match.value for match in matches][0]
    if isinstance(keys_next, dict):
        log = {}
        for k, v in keys_next.items():
            path_next = f'{path}.{k}'
            if v == -2:
                log[k] = get_json(depth + 1, path_next, log_indices, log_original)
            elif v == -1:
                log[k] = log_indices_base[k]
            else:
                log[k] = get_json(depth + 1, f'{path_next}[{v}]', log_indices, log_original)
        return log
    else:
        return keys_next


def get_log_json(log_original: dict) -> list:
    log_indices_all = {}
    log_json = []

    # 階層を1個深くして、配列に対応できるようにする
    log_original_deep = { 'ROOT': log_original }
    get_length_from_dict(log_original_deep, 0, '$', log_indices_all)

    # print(log_indices_all)
    # print(list(product_dict(log_indices_all)))
    # print(list(get_path(log_indices_all)))

    for log_indices in get_path(log_indices_all):
        log = get_json(0, '$', log_indices, log_original_deep)
        log_json.append(log['ROOT'])

    return log_json


if __name__ == '__main__':

    args = parse_args()

    if args.test:
        data_path = '../data_test'
    else:
        data_path = '../data'
    
    input_path = Path(os.path.dirname(__file__)) / data_path / 'input' / args.yaml_filename
    log_original = yaml.safe_load(open(input_path))

    log_json = get_log_json(log_original)

    if args.json:
        output_path = Path(os.path.dirname(__file__)) / data_path / 'output' / args.yaml_filename.replace(r'.yaml', '.json')
        with open(output_path, 'w') as f:
            f.write(json.dumps(log_json, indent=4))
    else:
        output_path = Path(os.path.dirname(__file__)) / data_path / 'output' / args.yaml_filename.replace(r'.yaml', '.jsonl')
        with open(output_path, 'w') as f:
            for log in log_json:
                f.write(json.dumps(log))
                f.write('\n')
