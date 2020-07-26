import argparse
import configparser
import logging
import time
from enum import Enum
from typing import List

from TM1py import TM1Service

from results import OptimusResult

APP_NAME = "optimuspy"
TIME_STAMP = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
LOGFILE = APP_NAME + ".log"
RESULT_CSV = "results\\{}_{}_{}.csv"
RESULT_PNG = "results\\{}_{}_{}.png"

logging.basicConfig(
    filename=LOGFILE,
    format="%(asctime)s - " + APP_NAME + " - %(levelname)s - %(message)s",
    level=logging.INFO,
)

config = configparser.ConfigParser()
config.read(r'config.ini')


class ExecutionMode(Enum):
    ALL = 0
    BRUTE_FORCE = 1
    ONE_SHOT = 2
    GREEDY = 3
    BEST = 4
    ORIGINAL_ORDER = 5

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        # default
        return cls.ALL


COLOR_MAP = {
    ExecutionMode.BRUTE_FORCE: "#1f77b4",
    ExecutionMode.ORIGINAL_ORDER: "silver",
    ExecutionMode.ONE_SHOT: "darkred",
    ExecutionMode.GREEDY: "#7000a0",
    ExecutionMode.BEST: "green",
    "Mean": "orange"}

LABEL_MAP = {
    ExecutionMode.BRUTE_FORCE: "Brute Force",
    ExecutionMode.ORIGINAL_ORDER: "Original Order",
    ExecutionMode.ONE_SHOT: "One Shot",
    ExecutionMode.GREEDY: "Greedy",
    ExecutionMode.BEST: "Best",
    "Mean": "Mean"}


def main(instance_name: str, cube_name: str, view_names: List[str], measure_dimension_only_numeric: bool,
         max_permutations: int, executions: int, mode: ExecutionMode):
    from executors import OriginalOrderExecutor, OneShotExecutor, GreedyExecutor, BruteForceExecutor, BestExecutor

    with TM1Service(**config[instance_name], session_context=APP_NAME) as tm1:
        original_dimension_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)
        displayed_dimension_order = tm1.cubes.get_dimension_names(cube_name=cube_name)

        try:
            permutation_results = list()

            original_order = OriginalOrderExecutor(
                tm1, cube_name, view_names, displayed_dimension_order, executions,
                measure_dimension_only_numeric, original_dimension_order)
            permutation_results += original_order.execute()

            # One Shot goes first, as it may blow up the overall RAM for the cube
            if mode == ExecutionMode.ALL or mode == ExecutionMode.ONE_SHOT:
                one_shot = OneShotExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric)
                permutation_results += one_shot.execute()

            if mode == ExecutionMode.ALL or mode == ExecutionMode.BRUTE_FORCE:
                brute_force = BruteForceExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, max_permutations)
                permutation_results += brute_force.execute()

            if mode == ExecutionMode.ALL or mode == ExecutionMode.GREEDY:
                greedy = GreedyExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric, max_permutations)
                permutation_results += greedy.execute()

            if mode == ExecutionMode.ALL or mode == ExecutionMode.BEST:
                best = BestExecutor(
                    tm1, cube_name, view_names, displayed_dimension_order, executions,
                    measure_dimension_only_numeric)
                permutation_results += best.execute()

            optimus_result = OptimusResult(cube_name, permutation_results, LABEL_MAP, COLOR_MAP)

            logging.info("Analysis Completed")
            logging.info("More details in csv and png files in results folder")
            for view_name in view_names:
                optimus_result.to_csv(view_name, RESULT_CSV.format(cube_name, view_name, TIME_STAMP))
                optimus_result.to_png(view_name, RESULT_PNG.format(cube_name, view_name, TIME_STAMP))
            return True

        except:
            logging.error("Fatal error", exc_info=True)
            return False

        finally:
            logging.info("Reestablishing original dimension order")
            tm1.cubes.update_storage_dimension_order(cube_name, original_dimension_order)


if __name__ == "__main__":
    # take arguments from cmd
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--instance',
                        action="store",
                        dest="instance_name",
                        help="name of the TM1 instance",
                        default=None)
    parser.add_argument('-c', '--cube',
                        action="store",
                        dest="cube_name",
                        help="name of the cube",
                        default=None)
    parser.add_argument('-v', '--views',
                        action="store",
                        dest="view_names",
                        help="comma separated list of cube views",
                        default=None)
    parser.add_argument('-n', '--numeric',
                        action="store",
                        dest="measure_dimension_only_numeric",
                        help="all measures are numeric elements (True=1, False=0)",
                        default=1)
    parser.add_argument('-p', '--permutations',
                        action="store",
                        dest="max_permutations",
                        help="maximum number of permutations to evaluate (required for BRUTE_FORCE or GREEDY mode)",
                        default=100)
    parser.add_argument('-e', '--executions',
                        action="store",
                        dest="executions",
                        help="number of executions per view",
                        default=15)
    parser.add_argument('-m', '--mode',
                        action="store",
                        dest="mode",
                        help="All, Brute_Force or One_Shot",
                        default="All")

    cmd_args = parser.parse_args()
    logging.info("Starting. Arguments retrieved from cmd: " + str(cmd_args))
    success = main(
        instance_name=cmd_args.instance_name,
        cube_name=cmd_args.cube_name,
        view_names=cmd_args.view_names.split(","),
        measure_dimension_only_numeric=bool(int(cmd_args.measure_dimension_only_numeric)),
        max_permutations=int(cmd_args.max_permutations),
        executions=int(cmd_args.executions),
        mode=ExecutionMode(cmd_args.mode))

    if success:
        logging.info("Finished successfully")
    else:
        exit(1)
