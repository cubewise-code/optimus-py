import argparse
import configparser
import logging
import sys
import time
from contextlib import suppress
from typing import Iterable, Union
from pathlib import Path

from TM1py import TM1Service
from mdxpy import MdxBuilder, Member, MdxHierarchySet

from executors import ExecutionMode, OriginalOrderExecutor, MainExecutor
from results import OptimusResult

APP_NAME = "optimuspy"
TIME_STAMP = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
LOGFILE = APP_NAME + ".log"
RESULT_PATH = Path("results/")
RESULT_CSV = "{}_{}_{}.csv"
RESULT_PNG = "{}_{}_{}.png"

COLOR_MAP = {
    ExecutionMode.ORIGINAL_ORDER: "silver",
    ExecutionMode.ITERATIONS: "#1f77b4",
    ExecutionMode.RESULT: "green",
    "Mean": "orange"}

LABEL_MAP = {
    ExecutionMode.ORIGINAL_ORDER: "Original Order",
    ExecutionMode.ITERATIONS: "Iterations",
    ExecutionMode.RESULT: "Result",
    "Mean": "Mean"}


def configure_logging():
    logging.basicConfig(
        filename=LOGFILE,
        format="%(asctime)s - " + APP_NAME + " - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # also log to stdout
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))


def get_tm1_config():
    config = configparser.ConfigParser()
    config.read(r'config.ini')
    return config


def convert_arg_to_bool(argument: Union[str, bool]):
    if isinstance(argument, bool):
        return argument
    else:
        if argument.lower() in ["true", "t"]:
            return True
        if argument.lower() in ["false", "f"]:
            return False
        raise ValueError("'{argument}' must be boolean or recognizable string")


def is_dimension_only_numeric(tm1: TM1Service, dimension_name: str) -> bool:
    if tm1.hierarchies.exists(dimension_name=dimension_name, hierarchy_name="Leaves"):
        hierarchy_name = "Leaves"
    else:
        hierarchy_name = dimension_name

    elements = tm1.elements.get_element_types(
        dimension_name=dimension_name,
        hierarchy_name=hierarchy_name,
        skip_consolidations=True)

    return all(e == "Numeric" for e in elements.values())


def build_vmm_vmt_mdx(cube_name: str):
    return MdxBuilder.from_cube("}CubeProperties") \
        .add_member_tuple_to_rows(Member.of("}Cubes", cube_name)) \
        .add_hierarchy_set_to_column_axis(
        MdxHierarchySet.members([
            Member.of("}CubeProperties", "VMM"),
            Member.of("}CubeProperties", "VMT")])) \
        .to_mdx()


def retrieve_vmm_vmt(tm1: TM1Service, cube_name: str) -> Iterable[str]:
    mdx = build_vmm_vmt_mdx(cube_name)
    return tm1.cells.execute_mdx_values(mdx)


def write_vmm_vmt(tm1: TM1Service, cube_name: str, vmm: str, vmt: str):
    mdx = build_vmm_vmt_mdx(cube_name)
    tm1.cells.write_values_through_cellset(mdx, [vmm, vmt])


def main(instance_name: str, view_name: str, executions: int, fast: bool):
    config = get_tm1_config()
    with TM1Service(**config[instance_name], session_context=APP_NAME) as tm1:
        model_cubes = filter(lambda c: not c.startswith("}"), tm1.cubes.get_all_names())
        for cube_name in model_cubes:
            if not tm1.cubes.views.exists(cube_name, view_name, private=False):
                logging.info(f"Skipping cube '{cube_name}' since view '{view_name}' does not exist")
                continue

            original_vmm, original_vmt = retrieve_vmm_vmt(tm1, cube_name)
            write_vmm_vmt(tm1, cube_name, "1000000", "1000000")

            logging.info(f"Starting analysis for cube '{cube_name}'")
            original_dimension_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)
            logging.info(f"Original dimension order for cube '{cube_name}' is: '{original_dimension_order}'")
            displayed_dimension_order = tm1.cubes.get_dimension_names(cube_name=cube_name)
            measure_dimension_only_numeric = is_dimension_only_numeric(tm1, original_dimension_order[-1])

            permutation_results = list()
            try:

                original_order = OriginalOrderExecutor(
                    tm1, cube_name, [view_name], displayed_dimension_order, executions,
                    measure_dimension_only_numeric, original_dimension_order)
                permutation_results += original_order.execute(reset_counter=True)

                main_executor = MainExecutor(
                    tm1, cube_name, [view_name], displayed_dimension_order, executions,
                    measure_dimension_only_numeric, fast)
                permutation_results += main_executor.execute()

                optimus_result = OptimusResult(cube_name, permutation_results)

                best_permutation = optimus_result.best_result
                logging.info(f"Completed analysis for cube '{cube_name}'")
                if not best_permutation:
                    logging.info(
                        f"No ideal dimension order found for cube '{cube_name}'."
                        f"Please pick manually based on csv and png results.")

                else:
                    best_order = best_permutation.dimension_order
                    tm1.cubes.update_storage_dimension_order(cube_name, best_order)
                    logging.info(f"Updated dimension order for cube '{cube_name}' to {best_order}")

            except:
                logging.error("Fatal error", exc_info=True)
                return False

            finally:
                with suppress(Exception):
                    write_vmm_vmt(tm1, cube_name, original_vmm, original_vmt)

                if len(permutation_results) > 0:
                    optimus_result = OptimusResult(cube_name, permutation_results)
                    optimus_result.to_csv(view_name, RESULT_PATH / RESULT_CSV.format(cube_name, view_name, TIME_STAMP))
                    optimus_result.to_png(view_name, RESULT_PATH / RESULT_PNG.format(cube_name, view_name, TIME_STAMP))
    return True


if __name__ == "__main__":
    configure_logging()

    # take arguments from cmd
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--instance',
                        action="store",
                        dest="instance_name",
                        help="name of the TM1 instance",
                        default=None)
    parser.add_argument('-v', '--view',
                        action="store",
                        dest="view_name",
                        help="the name of the cube view to exist in all cubes",
                        default=None)
    parser.add_argument('-e', '--executions',
                        action="store",
                        dest="executions",
                        help="number of executions per view",
                        default=15)
    parser.add_argument('-f', '--fast',
                        action="store",
                        dest="fast",
                        help="fast mode",
                        default=False)

    cmd_args = parser.parse_args()
    logging.info("Starting. Arguments retrieved from cmd: " + str(cmd_args))
    success = main(
        instance_name=cmd_args.instance_name,
        view_name=cmd_args.view_name,
        executions=int(cmd_args.executions),
        fast=convert_arg_to_bool(cmd_args.fast))

    if success:
        logging.info("Finished successfully")
    else:
        exit(1)
