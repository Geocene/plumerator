from plotting_test.plotter import main
from argparse import ArgumentParser
import os

parser = ArgumentParser()
parser.add_argument("-i", "--instr", action="store_true", default=False, help="run cli in instrument mode")
parser.add_argument("-r", "--reupload", help="run cli in reupload mode, needs filepath")

args = vars(parser.parse_args())

if args['reupload']:
	args['reupload'] = os.path.abspath(args['reupload'])

if __name__ == '__main__':
    main(instr=args['instr'], reupload=args['reupload'])

