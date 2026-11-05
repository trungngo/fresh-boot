" Personal overrides, sourced at the end of ~/.vimrc. Plain Vim: nothing here
" needs a plugin.

" Make sure vim runs in 256 colors
set t_Co=256
" A scheme that ships with Vim: habamax (Vim 9+), else desert (every Vim).
" (molokai was a plugin; it went with vim-plug.)
silent! colorscheme desert
silent! colorscheme habamax

nnoremap ; :

" Quickly go to normal mode
inoremap jj <esc>

" Quickly save a file
inoremap zz <esc>:w<CR>

" Quickly reformat a whole paragraph
inoremap kk <esc>gqipi

" Quickly reformat the whole paragraph
nnoremap F Jgqip

" Wild ignore for Unity
set wildignore+=*.meta

" Wild ignore for python
set wildignore+=*.pyc

" Wild ignore for web development
set wildignore+=*/tmp/*,*.so,*.swp,*.zip,solr/**,log/**,*.psd,*.PSD,.git/**
set wildignore+=.gitkeep,.gems/**
set wildignore+=*.ico,*.ICO,backup/**,*.sql,*.dump,*.tmp,*.min.js,Gemfile.lock
set wildignore+=*.png,*.PNG,*.JPG,*.jpg,*.JPEG,*.jpeg,*.GIF,*.gif,*.pdf,*.PDF
set wildignore+=vendor/**,coverage/**,tmp/**,rdoc/**,*.BACKUP.*,*.BASE.*
set wildignore+=*.LOCAL.*,*.REMOTE.*,.sass-cache/**

" Wildignore for javascript/nodejs
set wildignore+=*/bower_components/*,*/node_modules/*

" Turns of auto word wrap.
" See http://vim.wikia.com/wiki/Word_wrap_without_line_breaks
set linebreak
set nolist
set formatoptions-=t
set formatoptions+=l

" Quickly reload vim
nnoremap <leader>r :source $MYVIMRC<CR>

" Windows. The same keys the terminals (tmux, ghostty) use after their prefix,
" and the same as the IDEA/VS Code/Zed ports - see docs/keymap.md in this repository.
nnoremap <leader>v <C-w>v
nnoremap <leader>\ <C-w>v
nnoremap <leader>- <C-w>s
nnoremap <leader>h <C-w>h
nnoremap <leader>j <C-w>j
nnoremap <leader>k <C-w>k
nnoremap <leader>l <C-w>l
nnoremap <leader>H <C-w><
nnoremap <leader>J <C-w>-
nnoremap <leader>K <C-w>+
nnoremap <leader>L <C-w>>
nnoremap <Tab> <C-w>w
nnoremap <leader>z <C-w>_<C-w>|
nnoremap <leader>q <C-w>c


" Just enjoy my very first vim function
" This function convert a line into a snake variable
function! LineToRstLabelFunc(start_line, end_line)

    let search_for = '\s\+'
    let replace_with = '_'
    let modifiers = 'ge'

    " Duplicates and paste above
    normal! yyP

    " Selects the whole new line
    normal! 0v$

    exec a:start_line . "," . a:end_line . "s#" . search_for . '#' . replace_with . "#" . modifiers

    let lnum = line('.')
    let line = getline(lnum)
    let line = '.. _' . tolower(line) . ':'
    call setline(lnum, line)

endfunction

command! -range -bang LineToRstLabel call LineToRstLabelFunc(<line1>, <line2>)
