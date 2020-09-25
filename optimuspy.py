import argparse
import configparser
import logging
import time
from contextlib import suppress
from typing import Iterable

from TM1py import TM1Service
from mdxpy import MdxBuilder, Member, MdxHierarchySet

from executors import ExecutionMode
from executors import OriginalOrderExecutor, BestExecutor
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

COLOR_MAP = {
    ExecutionMode.BRUTE_FORCE: "green",
    ExecutionMode.ORIGINAL_ORDER: "silver",
    ExecutionMode.ONE_SHOT: "darkred",
    ExecutionMode.GREEDY: "#7000a0",
    ExecutionMode.BEST: "#1f77b4",
    "Mean": "orange"}

LABEL_MAP = {
    ExecutionMode.BRUTE_FORCE: "Brute Force",
    ExecutionMode.ORIGINAL_ORDER: "Original Order",
    ExecutionMode.ONE_SHOT: "One Shot",
    ExecutionMode.GREEDY: "Greedy",
    ExecutionMode.BEST: "Best",
    "Mean": "Mean"}


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


def main(instance_name: str, view_name: str, executions: int):
    with TM1Service(**config[instance_name], session_context=APP_NAME) as tm1:
        model_cubes = filter(lambda c: not c.startswith("}"), tm1.cubes.get_all_names())
        for cube_name in model_cubes:
            if not tm1.views.exists(cube_name, view_name, private=False):
                logging.info(f"Skipping cube '{cube_name}' since view '{view_name}' does not exist")
                continue

            original_vmm, original_vmt = retrieve_vmm_vmt(tm1, cube_name)
            write_vmm_vmt(tm1, cube_name, "1000000", "1000000")

            logging.info(f"Starting analysis for cube '{cube_name}'")
            original_dimension_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)
            displayed_dimension_order = tm1.cubes.get_dimension_names(cube_name=cube_name)
            measure_dimension_only_numeric = is_dimension_only_numeric(tm1, original_dimension_order[-1])

            permutation_results = list()
            try:

                original_order = OriginalOrderExecutor(
                    tm1, cube_name, [view_name], displayed_dimension_order, executions,
                    measure_dimension_only_numeric, original_dimension_order)
                permutation_results += original_order.execute(reset_counter=True)

                best = BestExecutor(
                    tm1, cube_name, [view_name], displayed_dimension_order, executions,
                    measure_dimension_only_numeric)
                permutation_results += best.execute()

                best_order = permutation_results[-1].dimension_order
                logging.info(f"Completed analysis for cube '{cube_name}'. Best order: {best_order}")

            except:
                logging.error("Fatal error", exc_info=True)
                return False

            finally:
                with suppress(Exception):
                    write_vmm_vmt(tm1, cube_name, original_vmm, original_vmt)

                if len(permutation_results) > 0:
                    optimus_result = OptimusResult(cube_name, permutation_results)
                    optimus_result.to_csv(view_name, RESULT_CSV.format(cube_name, view_name, TIME_STAMP))
                    optimus_result.to_png(view_name, RESULT_PNG.format(cube_name, view_name, TIME_STAMP))


if __name__ == "__main__":
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

    cmd_args = parser.parse_args()
    logging.info("Starting. Arguments retrieved from cmd: " + str(cmd_args))
    success = main(
        instance_name=cmd_args.instance_name,
        view_name=cmd_args.view_name,
        executions=int(cmd_args.executions))

    if success:
        logging.info("Finished successfully")
    else:
        exit(1)
