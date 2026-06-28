from bleu import BLEU
from exact_formula_match import Exact_Formula_Match
from formula_accuracy import Formula_Accuracy
from semantic_robustness import Semantic_Robustness
from strict_semantic_robustness import strict_semantic_robustness
from template_accuracy import Template_Accuracy

# file_path = "../result/direct_deepstl_with_deepseek_v4_pro_result.txt"
file_path = "../tmp/stl2stl.txt"

if __name__ == "__main__":
    Exact_formula_match_accuracy = Exact_Formula_Match(file_path)
    print("exact formula match accuracy: ", Exact_formula_match_accuracy)
    
    Formula_accuracy = Formula_Accuracy(file_path)
    print("formula accuracy: ", Formula_accuracy)

    Template_accuracy = Template_Accuracy(file_path)
    print("template accuracy: ", Template_accuracy)

    Bleu = BLEU(file_path)
    print("bleu: ", Bleu)

    Semantic_robustness = Semantic_Robustness(file_path)
    print("semantic robustness: ", Semantic_robustness)

    Strict_semantic_robustness = strict_semantic_robustness(file_path)
    print("strict semantic robustness: ", Strict_semantic_robustness)
