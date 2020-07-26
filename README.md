
# TM1 Optipyzer

Find the ideal dimension order for your TM1 cube

## Installing

Install TM1py:
```
pip install TM1py
```

Clone or download the `optimus-py` Repository from GitHub


## Usage

* Adjust config.ini to match your TM1 environments
* Execute the `optipyzer.py` script: 
```
C:\Projects\optimus-py\optimuspy.py -c="FIN General Ledger" -v="view1,view2" -e="10" -p="50" -m="All"
```

## Considerations
- Run on the same machine
- Use big views 
- Choose a sensible number of permutations for BruteForce and greedy mode
- OneShot mode requires DefaultMembers to be configured
- According to our tests, the `best` mode is the most auspicious


## Built With

* [requests](http://docs.python-requests.org/en/master/) - Python HTTP Requests for Humans
* [TM1py](https://github.com/cubewise-code/TM1py) - A python wrapper for the TM1 REST API


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
