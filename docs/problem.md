# 问题

## 架构层面
1. 在执行红队测试过程中 red-code-agent 是否参与其中，如果有，在哪些方面参与
2. 目前的流程是 创建operation->应用skill->内部创建jobs->运行->获得结果->展示结果(可选)。 目前并没有运行阶段
3. 我希望 red-code-agent 能够做成类似于 metasploit 的样式，将来扩展到 web 端
4. 当前red-code-agent所有操作均需要用户参与，并不智能，我希望 AI 能够全程参与其中，在初始化时创建operation，由用户输入必要的信息（名称，域名，IP等），然后由AI引导渗透测试，并不完全依赖用户的操作，而是由用户告知AI，AI引导Agent内部调用自行创建operation、jobs等。
5. task命令似乎完全用不上，可以删除
6. 需要保留Agent的对话功能，保留Agent的基础操作（文件读写），red-code-agent是基础agent+自动化AI测试agent的结合
7. 使用 harness 架构，对于一个operation，将其结果以memory形式存在文件中。
8. skill 对用户来说分为日常使用Skill和红队测试Skill，内部不需要区分，保留扩展性，以便于将来不创建operation也可以进行简单的红队测试，比如单次端口扫描任务
 

## 操作方面

1. operation 创建过于繁琐且没有默认选项，在红队测试中，首先会从IP或域名入手，此时没有端口、协议、工具等限制，只留下域名和IP，其他可以去除
2. operation,job,evidence,finding,planner 等均使用ID等区分，对用户并不友好

## 耦合度

要做的层次分明，UI、Agent循环、cli控制、工具调用等不应该耦合过高，方便后续的大修改。
