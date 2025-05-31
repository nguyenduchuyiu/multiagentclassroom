test = '[{"1": "1"}, {"1": "1"} {"1": "1"}]' #fixed: removed r prefix from string, lỗi có thể do thiếu dấu phẩy giữa các phần tử trong chuỗi JSON
import json
from ast import literal_eval
print(literal_eval(test))