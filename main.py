# -*- coding: utf-8 -*-
"""
jdepend:Java包依赖度量工具
功能: 代码分析
用法: python3 main.py
"""

import os
import json
import subprocess
import platform
import stat
import time

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET


class Jdepend(object):

    def generate_shell_file(self, cmd, log_flag=True, shell_name="tca_build"):
        """
        将编译命令保存到bash/bat的脚本文件中,并赋予可执行权限,返回执行该脚本文件的命令
        :return: 执行该脚本文件的命令
        """
        work_dir = os.getcwd()
        if platform.system() == "Windows":
            file_name = shell_name + ".bat"
        else:
            file_name = shell_name + ".sh"
        shell_filepath = os.path.join(work_dir, file_name)
        # 格式化文件路径
        shell_filepath = os.path.abspath(shell_filepath.strip()).replace('\\', '/').rstrip('/')
        with open(shell_filepath, "w") as wf:
            wf.write(cmd)
        # 给文件授权可执行权限
        os.chmod(shell_filepath, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

        if log_flag:
            print("cmd: %s" % cmd)
            print("generated shell file: %s" % shell_filepath)

        if platform.system() == "Windows":
            return shell_filepath
        else:
            return "bash %s" % shell_filepath

    def __get_task_params(self):
        """获取需要任务参数
        :return:
        """
        task_request_file = os.environ.get("TASK_REQUEST")
        with open(task_request_file, 'r') as rf:
            task_request = json.load(rf)
        task_params = task_request["task_params"]
        return task_params

    def compile(self, source_dir, build_cmd):
        """编译阶段
        """
        print("compile start")
        if not build_cmd:
            raise Exception("Jdepend依赖编译，需要输入编译命令，请填入编译命令后重试！")
        build_cmd = self.generate_shell_file(build_cmd)
        print("build cmd: %s" % build_cmd)
        start = time.time()
        # 检查命令行是否有注入字符，并给出提示
        spc = subprocess.Popen(
            build_cmd,
            cwd=source_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True
        )
        while spc.poll() is None:
            line = spc.stdout.readline().strip()
            if line:
                print(line.decode("utf-8", "ignore"))
        if spc.returncode != 0:
            raise Exception('compile failed with return code: %d' % spc.returncode)
        print("compile done, cost time: %s" % (time.time() - start))

    def run(self):
        """
        :return:
        """
        # 代码目录直接从环境变量获取
        source_dir = os.environ.get("SOURCE_DIR", None)
        print("[debug] source_dir: %s" % source_dir)
        # 结果目录直接从环境变量获取
        result_dir = os.environ.get("RESULT_DIR", os.getcwd())
        # 其他参数从task_request.json文件获取
        task_params = self.__get_task_params()
        # 环境变量
        envs = task_params["envs"]
        print("[debug] envs: %s" % envs)
        # 规则
        rules = task_params["rules"]

        self.compile(source_dir, task_params.get("build_cmd", ""))

        jdepend_output = os.path.join(result_dir, "jdepend_output.xml")
        result=[]

        java_bin = os.path.join(os.environ["JDK_11_HOME"], "bin", "java")
        cmd = [
            java_bin,
            "-cp",
            "lib/jdepend-2.10.jar",
            "jdepend.xmlui.JDepend",
            "-file",
            jdepend_output,
            source_dir
        ]

        scan_cmd = " ".join(cmd)
        print("[debug] cmd: %s" % scan_cmd)
        # 优化调用方式
        subproc = subprocess.Popen(scan_cmd, shell=True)
        subproc.communicate()

        print("start data handle")
        # 数据处理
        result_path = os.path.join(result_dir, "result.json")
        if not os.path.exists(jdepend_output) or os.stat(jdepend_output).st_size == 0:
            print("[error] result is empty")
            with open(result_path, "w") as fp:
                json.dump(result, fp, indent=2)
            return

        config = ET.ElementTree(file=jdepend_output)
        for analyzer in config.iter(tag="Cycles"):
            for node in analyzer:
                current_package = node.attrib.get("Name")
                depend_packages = [package.text for package in node]
                if current_package in depend_packages:
                    issue = {}
                    issue['path'] = ".TCA_PROJECT_SUMMARY"
                    issue['line'] = 0
                    issue['column'] = 0
                    issue['msg'] = "Package(%s)存在依赖循环: %s" % (current_package, "->".join(depend_packages))
                    issue['rule'] = "Package_Dependency_Cycles"
                    issue['refs'] = []
                    if issue['rule'] not in rules:
                        continue
                    result.append(issue)

        # 输出结果到指定的json文件
        with open(result_path, "w") as fp:
            json.dump(result, fp, indent=2)


if __name__ == '__main__':
    print("-- start run tool ...")
    Jdepend().run()
    print("-- end ...")
