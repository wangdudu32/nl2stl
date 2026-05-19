各文件内容解释:
deepstl_test_2k.csv:存储着deepstl测试集2k条原数据
1_deepstl_sig_para.csv:对deepstl_test_2k.csv数据集预处理(将所有的变量全部参数化sig1,sig2,sig3,...)之后的结果;
2_deepstl_structure.csv:将1_deepstl_sig_para.csv的nl部分去掉了,然后进行了去重
2_deepstl_structure_para.csv:对2_deepstl_structure.csv文件中的信号的值和时间数值(!0)进行了参数化(val1,val2,val3,...)(t1,t2,t3,...),然后进行了去重
2_deepstl_structure_para_reduced.csv:对2_deepstl_structure_para.csv文件内容进行了去重
2_deepstl_structure_final.csv:对2_deepstl_structure_para_reduced.csv内容进行了谓词参数化,得到了最终的deepstl模板


