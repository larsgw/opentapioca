import numpy
import json
from scipy import sparse
from .dumpreader import WikidataDumpReader

class WikidataGraph(object):
    def preprocess_dump(self, fname, output_fname):
        """
        Compresses a JSON Wikidata dump in a custom, smaller format
        that only stores the edges and their weights. This file should
        then be sorted (for instance with GNU sort) before being loaded
        as a preprocessed dump.
        """
        output_file = open(output_fname, 'w')

        with WikidataDumpReader(fname) as reader:
            for item in reader:
                qid = item['id']
                if qid[0] != 'Q':
                    continue

                rowid = int(qid[1:])
                if rowid % 10000 == 0:
                    print(str(rowid))

                edges = item.get_outgoing_edges()
                nb_edges = len(edges)
                if not nb_edges:
                    continue

                ordered_edges = list(sorted(set(edges)))
                target_to_idx = { x:i for i,x in enumerate(ordered_edges) }
                cur_data = [0 for x in ordered_edges]
                for target in edges:
                    cur_data[target_to_idx[target]] += 1

                fields = [str(rowid),
                    json.dumps(ordered_edges),
                    json.dumps(cur_data),
                ]
                output_file.write('\t'.join(fields)+'\n')

    def load_from_preprocessed_dump(self, fname):
        """
        Loads the preprocessed dump in a sparse matrix
        """
        batch_size = 1000000
        data_lst = []
        indices_lst = []
        indptr = [0]
        nonempty_indices = []
        row_offset = 0
        block_matrices = []

        # First, read the last qid
        with open(fname, 'r') as f:
            for last in f:
                pass
            last_qid = int(last.split('\t')[0])
        print('Last QID: Q%d' % last_qid)

        with open(fname, 'r') as f:

            for line in f:
                fields = line.strip().split('\t')
                qid = int(fields[0])
                indices = json.loads(fields[1])
                counts = json.loads(fields[2])

                # pad with empty rows so that we stay in sync
                while row_offset + len(indptr) <= qid:
                    indptr.append(len(data_lst))

                if indices:
                    nonempty_indices.append(qid)
                    sum_counts = float(sum(counts))
                    weights = [count / sum_counts for count in counts]
                    data_lst += weights
                    indices_lst += indices
                    indptr.append(len(data_lst))

                if len(nonempty_indices) % batch_size == 0 or qid == last_qid:
                    print(len(nonempty_indices))
                    mat = sparse.csr_matrix((data_lst, indices_lst, indptr), shape=(len(indptr)-1,last_qid+1))
                    block_matrices.append(mat)
                    row_offset += len(indptr) - 1
                    data_lst = []
                    indices_lst = []
                    indptr = [0]

        self.mat = sparse.vstack(block_matrices)
        self.N = len(nonempty_indices)
        self.shape = len(indptr)

    def load_from_matrix(self, fname):
        self.mat = sparse.load_npz(fname)
        self.shape = self.mat.shape[1]

    def save_matrix(self, fname):
        sparse.save_npz(fname, self.mat)

    def compute_pagerank(self):
        N = self.mat.shape[0]
        print(N)
        # create uniform vector
        data = [1./N] * N
        rows = [0]*N
        cols = list(range(N))
        v = sparse.csr_matrix((data, (rows, cols)), shape=(1,N))

        max_iterations = 32
        for i in range(max_iterations):
            print('---- %d ----' % i)
            nv = v.dot(self.mat)

            # loss compensation
            l1norm = nv.sum()
            comp = sparse.csr_matrix(([(1. - l1norm)/N]*N, (rows, cols)), shape=(1,N))
            nv += comp

            # convergence control
            diff = nv - v
            div = diff.multiply(diff.sign()).sum()
            print(div)

            # update
            v = nv
        self.pagerank = v.todense()

    def load_pagerank(self, fname):
        self.pagerank = numpy.load(fname)

    def save_pagerank(self, fname):
        numpy.save(fname, self.pagerank)

    def get_pagerank(self, qid):
        id = int(qid[1:])
        if id < self.pagerank.shape[1]:
            return self.pagerank[(0,int(qid[1:]))]
        else:
            return 0.01/self.pagerank.shape[1]

    def compute_similarity(self, qida, qidb, steps=3, beta=0.5, explain=False):
        """
        Compute the similarity between two qids
        """
        va = self._get_neighbour_vector(int(qida[1:]), steps, beta)
        vb = self._get_neighbour_vector(int(qidb[1:]), steps, beta)
        dp = va.dot(vb.transpose())
        if explain:
            self._print_neighbours(va)
            self._print_neighbours(vb)
            prod = va.multiply(vb)
            non_zero = prod.nonzero()[1]
            best_id = 0
            best_score = 0
            for idx in range(len(non_zero)):
                score = prod[0,non_zero[idx]]
                if score > best_score:
                    best_score = score
                    best_id = non_zero[idx]
            print('https://www.wikidata.org/wiki/Q%d' % best_id)
        return dp[0,0]

    def _get_neighbour_vector(self, id, steps, beta):
        """
        Returns the neighbour vector after a few iterations of the matrix
        """
        N = self.mat.shape[0]
        initial_v = sparse.csr_matrix(([1],([0],[id])), shape=(1,N))
        v = initial_v
        for k in range(steps):
            nv = v.dot(self.mat)

            # loss compensation and recurrence
            l1norm = nv.sum()
            if l1norm == 0:
                return v
            nv *= (1./l1norm)*(1-beta)
            nv += beta*initial_v

            # update
            v = nv

        return v

    def _print_neighbours(self, neighbour_vector):
        non_zero = neighbour_vector.nonzero()[1]
        for idx in range(len(non_zero)):
            print('\t'.join([str(neighbour_vector[0,non_zero[idx]]), 'https://www.wikidata.org/wiki/Q%d' % non_zero[idx]]))

