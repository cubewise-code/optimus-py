
![](https://github.com/cubewise-code/optimus-py/blob/master/images/logo.png)

# OptimusPy for TM1

Find the ideal dimension order for your TM1 cubes

## Installing

Install required python packages:
```
pip install TM1py
pip install seaborn
```

Clone or download the `optimus-py` Repository from GitHub


## Usage

* Adjust config.ini to match your TM1 environment
* Create uniquely named views in the relevant cubes
* Execute the `optimuspy.py` 
* provide 8 arguments: 
    -i _(name of the instance)_ 
    -c _(name of the cube)_ 
    -v _(name of the cube view)_ 
    -e _(number of execution)_ 
    -f _(fast mode: True or False)_
    -o _(output: csv or xlsx)_ 
    -u _(update original order: True or False)_
    -t _(name of a ti process to measure runtime)_
    -d _(optional: comma split list of dimensions to keep positions as per the storage order)_

```
C:\Projects\optimus-py\optimuspy.py -i="tm1srv01" -c="Cube Name" -v="Optimus" -e="10" -f="True" -o="csv" -u=True -t="load.csv.file"
```

```
C:\Projects\optimus-py\optimuspy.py --instance="tm1srv01" --cube="Cube Name" --view="Optimus" --executions="15" --fast="True" --output="csv" --update=True --process="load.csv.file"
```

## Output

OptimusPy determines the ideal dimension order for every cube, based on RAM and query speed.
For traceability and custom analysis, Optimus visualizes the results in a csv report and a scatter plot per cube.


|ID |Mode          |Mean Query Time|RAM   |Dimension1   |Dimension2  |Dimension3  |Dimension4  |Dimension5   |Dimension6  |Dimension7|Dimension8|Dimension9   |
|---|--------------|---------------|------|-------------|------------|------------|------------|-------------|------------|----------|----------|-------------|
|1  |Original Order|0.00445528     |259072|Industry     |SalesMeasure|Product     |Executive   |Business Unit|Customer    |Version   |State     |Time         |
|2  |Iterations    |0.00379407     |520184|SalesMeasure |Customer    |Executive   |Industry    |Product      |State       |Time      |Version   |Business Unit|
|3  |Iterations    |0.00378995     |520184|Business Unit|SalesMeasure|Executive   |Industry    |Product      |State       |Time      |Version   |Customer     |
|4  |Iterations    |0.00422788     |520184|Business Unit|Customer    |SalesMeasure|Industry    |Product      |State       |Time      |Version   |Executive    |
|5  |Iterations    |0.00458372     |520184|Business Unit|Customer    |Executive   |SalesMeasure|Product      |State       |Time      |Version   |Industry     |
|6  |Iterations    |0.00479290     |259072|Business Unit|Customer    |Executive   |Industry    |SalesMeasure |State       |Time      |Version   |Product      |
|7  |Iterations    |0.00548539     |259072|Business Unit|Customer    |Executive   |Industry    |Product      |SalesMeasure|Time      |Version   |State        |

![](https://github.com/cubewise-code/optimus-py/blob/master/images/scatter_plot.png)

## Considerations
- Run on the same machine
- Use big and representative views 
- Choose a sensible number of `executions`
- Provide enough spare memory on TM1 server
- Fast mode determines first and last position only

## Need a .exe version of OptimusPy?

The latest executable build is available as an artifact in the GitHub Actions workflow runs. To download it:

1. Go to the [Actions tab](https://github.com/cubewise-code/optimus-py/actions) of the repository.
2. Click on the most recent workflow run titled **Build Executable**.
3. In the workflow summary, look for the **Artifacts** section.
4. Download the **optimuspy-winOS** artifact.

## Built With

* [TM1py](https://github.com/cubewise-code/TM1py) - A python wrapper for the TM1 REST API
* [matplotlib](https://github.com/matplotlib/matplotlib) - A comprehensive library for crating visualizations in Python.


## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details
