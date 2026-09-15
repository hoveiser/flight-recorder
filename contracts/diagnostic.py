# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

import json
import genlayer as gl


class Diagnostic(gl.contract.Contract):
    results: gl.storage.TreeMap[str, str]

    def __init__(self):
        pass

    @gl.public.write
    def test_web_fetch(self, url: str):
        def leader_fn():
            text = gl.nondet.web.render(url, mode="text")
            return {"length": len(text), "preview": text[:100]}

        def validator_fn(leader_result):
            if not isinstance(leader_result, gl.vm.Return):
                return False
            return True

        try:
            result = gl.vm.run_nondet(leader_fn, validator_fn)
            self.results["web_fetch"] = json.dumps({"success": True, **result})
        except Exception as e:
            self.results["web_fetch"] = json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__})

    @gl.public.write
    def test_llm_call(self):
        def leader_fn():
            prompt = "Say hello in JSON: {\"message\": \"<greeting>\"}"
            obj = gl.nondet.exec_prompt(prompt, response_format="json")
            return {"response": obj}

        def validator_fn(leader_result):
            if not isinstance(leader_result, gl.vm.Return):
                return False
            return True

        try:
            result = gl.vm.run_nondet(leader_fn, validator_fn)
            self.results["llm_call"] = json.dumps({"success": True, **result})
        except Exception as e:
            self.results["llm_call"] = json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__})

    @gl.public.write
    def test_combined(self, url: str):
        def leader_fn():
            text = gl.nondet.web.render(url, mode="text")
            if len(text) < 20:
                return {"error": "text too short", "length": len(text)}
            case = json.loads(text)
            prompt = "Respond with JSON: {\"verdict\": \"APPROVED\" or \"REFUNDED\", \"reasoning\": \"<one sentence>\"}"
            obj = gl.nondet.exec_prompt(prompt, response_format="json")
            return {"case_keys": list(case.keys()), "llm_response": obj}

        def validator_fn(leader_result):
            if not isinstance(leader_result, gl.vm.Return):
                return False
            return True

        try:
            result = gl.vm.run_nondet(leader_fn, validator_fn)
            self.results["combined"] = json.dumps({"success": True, **result})
        except Exception as e:
            self.results["combined"] = json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__})

    @gl.public.view
    def get_results(self) -> str:
        return json.dumps({k: json.loads(v) for k, v in self.results.items()})

    @gl.public.view
    def get_result(self, key: str) -> str:
        return self.results.get(key, "{}")
