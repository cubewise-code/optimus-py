
# TM1 Optimus-py

Find the ideal dimension order for your TM1 cubes

## Installing

Install TM1py:
```
pip install TM1py
```

Clone or download the `optimus-py` Repository from GitHub


## Usage

* Adjust config.ini to match your TM1 environment
* Create uniquely named views in the relevant cubes
* Execute the `optimuspy.py` script: 

```
C:\Projects\optimus-py\optimuspy.py -i="tm1srv01" -v="Optimus" -e="10"
```

```
C:\Projects\optimus-py\optimuspy.py --instance="tm1srv01" --view="Optimus" --executions="15"
```

## Output

Optimus determines the ideal dimension order for every cube, based on RAM and query speed.
For traceability and further analysis, Optimus visualizes the results in a csv report and a scatter plot for every cube.


|ID |Mode          |Mean Query Time|RAM   |RAM Change in %|Dimension1   |Dimension2  |Dimension3  |Dimension4  |Dimension5   |Dimension6  |Dimension7|Dimension8|Dimension9   |
|---|--------------|---------------|------|---------------|-------------|------------|------------|------------|-------------|------------|----------|----------|-------------|
|1  |Original Order|0.00445528     |259072|0.00 %         |Industry     |SalesMeasure|Product     |Executive   |Business Unit|Customer    |Version   |State     |Time         |
|2  |Best          |0.00379407     |520184|100.79 %       |SalesMeasure |Customer    |Executive   |Industry    |Product      |State       |Time      |Version   |Business Unit|
|3  |Best          |0.00378995     |520184|0.00 %         |Business Unit|SalesMeasure|Executive   |Industry    |Product      |State       |Time      |Version   |Customer     |
|4  |Best          |0.00422788     |520184|0.00 %         |Business Unit|Customer    |SalesMeasure|Industry    |Product      |State       |Time      |Version   |Executive    |
|5  |Best          |0.00458372     |520184|0.00 %         |Business Unit|Customer    |Executive   |SalesMeasure|Product      |State       |Time      |Version   |Industry     |
|6  |Best          |0.00479290     |259072|-50.20 %       |Business Unit|Customer    |Executive   |Industry    |SalesMeasure |State       |Time      |Version   |Product      |
|7  |Best          |0.00548539     |259072|0.00 %         |Business Unit|Customer    |Executive   |Industry    |Product      |SalesMeasure|Time      |Version   |State        |

![](https://github.com/cubewise-code/optimus-py/blob/master/images/scatter_best_mode.png)

## Considerations
- Run on the same machine
- Use big views 
- Choose a sensible number of `executions`


## Built With

* [requests](http://docs.python-requests.org/en/master/) - Python HTTP Requests for Humans
* [TM1py](https://github.com/cubewise-code/TM1py) - A python wrapper for the TM1 REST API


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
