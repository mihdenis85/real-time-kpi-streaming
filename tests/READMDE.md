First, get the dependencies. In project root folder, run:

```shell
pip install tests/requirements.txt
```

Run tests in `/tests` folder. In Project root folder, run:

```shell
pytest -q -rA tests/ | tee test_results.log
```
