import datetime
import json
import os
import psycopg2  # PostgreSQL用ライブラリ
import requests
import websocket
from psycopg2.extras import execute_values

# IE:作業者分析で使う値
elapsed_time_limit = 10  # 前フレームからこの秒数以上経過した場合はDBへの出力は行わない。
bef_time = None

# 利用するコンポ(『IE:作業者分析』『RT:購買行動分析』『SB:不審行動検知』)
aiipf_compo = os.environ["AIIPF_COMPO"]

# ACT-SDKの設定、REST-APIでデータ送信時に仕様
actsdk = os.environ["ACTSDK_RESTAPI"]

# DB関係の設定
connection_str = os.environ["DB_CONNECT_STR"]
table_name = os.environ["TABLE_NAME"]
act_id = os.environ["ACT_ID"]

# MODEクラウドへの接続設定
url = os.environ["MODE_ADDR"]

headers = ["Authorization: ModeCloud " + os.environ["MODE_TOKEN"]]

# DBとの接続
connection = psycopg2.connect(connection_str)


# 『SB:不審行動検知』用のデータ受信処理
def receive_data_sb(wsapp, message):
    insert_list = []
    json_dict = json.loads(message)
    print(
        "SequenceNumber: ",
        json_dict["SequenceNumber"],
        "Time: ",
        json_dict["AnalysisDatetime"],
    )

    # データ形式がActDataの時だけ送信する。
    if json_dict["PayloadType"][0] == "ActData":
        # DBへのデータ出力
        for cameraId, result in enumerate(json_dict["Payload"]["Results"]):
            for ruleinfo in result["ScenarioRecog"]["BehaviorArray"]:
                # 不審者分析の時だけACT-SDK側で警告表示を行うかどうかのフラグをセットする。
                result["ScenarioRecog"]["Caution"] = True

                if not ruleinfo["TimeInfo"]["EndTime"] is None:
                    # 動画ファイルを使う場合、EndTimeに動画ファイルの更新日時をベースとした
                    data = (
                        act_id,
                        cameraId,
                        ruleinfo["TimeInfo"]["EndTime"],
                        ruleinfo["RuleLabel"],
                        ruleinfo["TimeInfo"]["ElapsedTime"],
                    )
                    insert_list.append(data)
                    print(data)

        if len(insert_list) > 0:
            cur = connection.cursor()
            execute_values(cur, "INSERT INTO " + table_name + " values %s", insert_list)
            connection.commit()

        # 映像データがある場合はACT-SDKのREST-APIにデータ送信
        if json_dict["Payload"]["Results"][0]["FrameInfo"] != {}:
            response = requests.post(actsdk, json=json_dict)
            print(
                "REST-API SEND SeqNo:{} response:{}".format(
                    json_dict["SequenceNumber"], response
                )
            )


# 『IE:作業者分析』用のデータ受信処理
def receive_data_ie(wsapp, message):
    global bef_time
    insert_list = []
    json_dict = json.loads(message)
    print(
        "SequenceNumber: ",
        json_dict["SequenceNumber"],
        "Time: ",
        json_dict["AnalysisDatetime"],
    )

    # データ形式がActDataの時だけ送信する。
    if json_dict["PayloadType"][0] == "ActData":
        # 送られてきたJsonデータの時間を取得
        now_time = datetime.datetime.strptime(
            json_dict["Payload"]["Results"][0]["ScenarioRecog"]["FrameInfo"]["Time"],
            "%Y-%m-%d %H:%M:%S.%f%z",
        )
        # 初回の場合だけ
        if bef_time is None:
            bef_time = now_time

        elapsed_time = (now_time - bef_time).total_seconds()

        if elapsed_time > 0 and elapsed_time < elapsed_time_limit:
            # DBへのデータ出力
            for cameraId, result in enumerate(json_dict["Payload"]["Results"]):
                for ruleinfo in result["ScenarioRecog"]["BehaviorArray"]:
                    data = (
                        act_id,
                        cameraId,
                        result["ScenarioRecog"]["FrameInfo"]["Time"],
                        ruleinfo["RuleLabel"],
                        elapsed_time,
                    )
                    insert_list.append(data)
                    print(data)

            if len(insert_list) > 0:
                cur = connection.cursor()
                execute_values(
                    cur, "INSERT INTO " + table_name + " values %s", insert_list
                )
                connection.commit()

        # 現フレームの時刻を次回Jsonデータ受信時の前回フレームの時刻としてセット
        bef_time = now_time

        # 映像データがある場合はACT-SDKのREST-APIにデータ送信
        if json_dict["Payload"]["Results"][0]["FrameInfo"] != {}:
            response = requests.post(actsdk, json=json_dict)
            print(
                "REST-API SEND SeqNo:{} response:{}".format(
                    json_dict["SequenceNumber"], response
                )
            )


def on_error(ws, error):
    pass


tracemode = os.getenv("TRACE_MODE")
if tracemode is not None and tracemode.upper() == "TRUE":
    print("WebSocketをトレースモードで実行")
    websocket.enableTrace(True)

# AIIPF_COMPOで設定されたコンポに合わせて
if aiipf_compo == "IE":
    on_message = receive_data_ie
elif aiipf_compo == "SB" or aiipf_compo == "RT":
    on_message = receive_data_sb
else:
    print("There is no compo specified by AIIPF_COMPO.")
    exit()

print("AIIPF_COMPO: " + aiipf_compo)
print("MODE Cloud Connect")
wsapp = websocket.WebSocketApp(
    url, header=headers, on_message=on_message, on_error=on_error
)
wsapp.run_forever(suppress_origin=True, reconnect=5)
