#!/bin/bash
uri=127.0.0.1
port=8080
runs=file:///home/stef/quest_data/hiec/results/runs
mlflow ui --host $uri --port $port --backend-store-uri $runs